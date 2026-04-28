import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.backend.database import init_db
from src.backend.config import settings
from src.backend.routes import leagues, players, teams, draft, market, scoring


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    print("Initializing database...")
    await init_db()

    if settings.SIMULATOR_API_URL:
        print(f"Simulator API configured: {settings.SIMULATOR_API_URL}")
        print("Player data will be fetched live from wc-simulator.")
        # Sync country metadata (names, flags) from simulator on startup so
        # the UI can render flags. Idempotent — updates rows that exist.
        try:
            from src.backend.services.simulator_client import fetch_countries
            from src.backend.database import get_db
            countries = await fetch_countries()
            db = await get_db()
            try:
                for c in countries:
                    await db.execute(
                        """INSERT INTO countries (code, name, flag, confederation)
                           VALUES ($1, $2, $3, $4)
                           ON CONFLICT (code) DO UPDATE SET
                               name = EXCLUDED.name,
                               flag = COALESCE(EXCLUDED.flag, countries.flag),
                               confederation = COALESCE(EXCLUDED.confederation, countries.confederation)""",
                        (c.get("code"), c.get("name") or c.get("code"),
                         c.get("flag"), c.get("confederation")),
                    )
                await db.commit()
                print(f"Synced {len(countries)} countries from simulator (flags + names)")
            finally:
                await db.close()
        except Exception as e:
            print(f"Country sync skipped: {e}")
    else:
        print("⚠️  No SIMULATOR_API_URL configured.")
        print("   Set SIMULATOR_API_URL to point to wc-simulator for player data.")

    # Start autodraft watchdog: resumes drafts stuck on bot/autodraft turns
    # (e.g. after a pod restart mid-cascade)
    watchdog_task = asyncio.create_task(_autodraft_watchdog())

    # Start market window auto-transition watchdog
    market_watchdog_task = asyncio.create_task(_market_auto_transition_watchdog())

    # Start auto market-window creator (creates windows when each phase finishes)
    auto_market_creator_task = asyncio.create_task(_auto_market_window_creator())

    yield

    watchdog_task.cancel()
    market_watchdog_task.cancel()
    auto_market_creator_task.cancel()
    try:
        await watchdog_task
    except asyncio.CancelledError:
        pass
    try:
        await market_watchdog_task
    except asyncio.CancelledError:
        pass
    try:
        await auto_market_creator_task
    except asyncio.CancelledError:
        pass

    # Cleanup httpx client on shutdown
    if settings.SIMULATOR_API_URL:
        from src.backend.services.simulator_client import close_client
        await close_client()


async def _autodraft_watchdog():
    """Periodically resume any in-progress draft whose current team is on autodraft
    or has a queue. Robust against pod restarts mid-cascade."""
    from src.backend.database import get_db
    from src.backend.services.draft_engine import DraftEngine
    from src.backend.routes.draft import _process_and_broadcast_autodraft

    print("Autodraft watchdog started.")
    while True:
        try:
            # Long interval: WS connect already resumes drafts. This is just a
            # safety net for fully-bot drafts with no clients connected.
            await asyncio.sleep(120)
            db = await get_db()
            try:
                rows = await db.execute_fetchall(
                    "SELECT league_id FROM drafts WHERE status='in_progress'"
                )
            finally:
                await db.close()
            for row in rows:
                league_id = row["league_id"]
                # Defensive: ensure all bots in this league have autodraft enabled
                # (in case they were created/reset without it being re-enabled).
                try:
                    from src.backend.services.bot_service import enable_autodraft_for_bots
                    await enable_autodraft_for_bots(league_id)
                except Exception:
                    pass
                state = await DraftEngine.get_draft_state(league_id)
                if not state or state["status"] != "in_progress":
                    continue
                current_team = state.get("current_team_id")
                if not current_team:
                    continue
                has_auto = await DraftEngine.is_autodraft(league_id, current_team)
                has_queue = await DraftEngine.has_queue(league_id, current_team)
                if has_auto or has_queue:
                    print(f"[autodraft watchdog] resuming league={league_id} team={current_team}")
                    try:
                        await _process_and_broadcast_autodraft(league_id)
                    except Exception as e:
                        print(f"[autodraft watchdog] error: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[autodraft watchdog] loop error: {e}")


def _parse_iso(s: str):
    """Parse an ISO datetime string to a tz-aware UTC datetime.

    Naive strings (no timezone) are interpreted as Europe/Madrid local time,
    matching what the frontend datetime-local input sends.
    """
    from datetime import datetime, timezone
    try:
        from zoneinfo import ZoneInfo
        MADRID = ZoneInfo("Europe/Madrid")
    except Exception:
        MADRID = timezone.utc  # fallback if tzdata missing
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=MADRID)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


async def _market_auto_transition_watchdog():
    """Automatically transition market windows when their phases end."""
    from src.backend.database import get_db
    from src.backend.services.market_service import MarketService
    from datetime import datetime, timezone

    print("Market auto-transition watchdog started.")
    while True:
        try:
            await asyncio.sleep(60)  # Check every minute
            db = await get_db()
            try:
                # Get all non-completed market windows
                windows = await db.execute_fetchall(
                    """SELECT * FROM market_windows 
                       WHERE status != 'completed'
                       ORDER BY clause_window_start ASC"""
                )
            finally:
                await db.close()

            now_dt = datetime.now(timezone.utc)

            for window in windows:
                try:
                    status = window["status"]

                    # pending → clause_window
                    if (status == "pending" and
                        window["clause_window_start"] and
                        now_dt >= (_parse_iso(window["clause_window_start"]) or now_dt)):
                        print(f"[market watchdog] transitioning window {window['id']} to clause_window")
                        await MarketService.start_clause_phase(window["id"])
                        continue

                    # clause_window → market_open
                    if (status == "clause_window" and
                        window["clause_window_end"] and
                        now_dt >= (_parse_iso(window["clause_window_end"]) or now_dt)):
                        print(f"[market watchdog] transitioning window {window['id']} to market_open")
                        await MarketService.start_market_phase(window["id"])

                    # market_open → market_closed
                    elif (status == "market_open" and
                          window["market_window_end"] and
                          now_dt >= (_parse_iso(window["market_window_end"]) or now_dt)):
                        print(f"[market watchdog] transitioning window {window['id']} to market_closed")
                        await MarketService.close_market(window["id"])

                    # market_closed → reposition_draft
                    elif (status == "market_closed" and
                          window["reposition_draft_start"] and
                          now_dt >= (_parse_iso(window["reposition_draft_start"]) or now_dt)):
                        print(f"[market watchdog] transitioning window {window['id']} to reposition_draft")
                        await MarketService.start_reposition_draft(window["id"])

                    # reposition_draft → completed
                    elif (status == "reposition_draft" and
                          window["reposition_draft_end"] and
                          now_dt >= (_parse_iso(window["reposition_draft_end"]) or now_dt)):
                        print(f"[market watchdog] transitioning window {window['id']} to completed")
                        db = await get_db()
                        try:
                            await db.execute(
                                "UPDATE market_windows SET status='completed', updated_at=$1 WHERE id=$2",
                                (now_dt.isoformat(), window["id"]),
                            )
                            await db.commit()
                        finally:
                            await db.close()

                except Exception as e:
                    print(f"[market watchdog] error transitioning window {window['id']}: {e}")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[market watchdog] loop error: {e}")


# Phases that get an auto-generated market window when the previous phase finishes.
# Tuple: (source_phase_that_just_finished, target_phase_for_window)
_AUTO_MARKET_TRANSITIONS = [
    ("groups", "r32"),
    ("r32", "r16"),
    ("r16", "quarter"),
    ("quarter", "semi"),
    ("semi", "final"),
]


async def _auto_market_window_creator():
    """Periodically check active leagues; when all matchdays of a phase that
    feeds into a knockout round are finished, automatically create a market
    window for the next phase (clause/market/reposition draft, 1 day each)."""
    from src.backend.database import get_db
    from src.backend.services.market_service import MarketService
    from datetime import datetime, timezone, timedelta

    print("Auto market-window creator started.")
    while True:
        try:
            await asyncio.sleep(60)
            db = await get_db()
            try:
                # Active leagues only (draft completed and tournament running)
                leagues_rows = await db.execute_fetchall(
                    "SELECT id FROM leagues WHERE status IN ('active', 'in_progress')"
                )
                # Phase completion status (global — matchdays are shared across leagues)
                md_rows = await db.execute_fetchall(
                    "SELECT phase, status FROM matchdays"
                )
            finally:
                await db.close()

            # Backfill: ensure every active league has the 5 pre-created
            # pending windows (handles leagues that became active before
            # this feature was added).
            for lg in leagues_rows:
                try:
                    await MarketService.ensure_league_market_windows(lg["id"])
                except Exception as e:
                    print(f"[auto-market] backfill error league={lg['id']}: {e}")

            phase_totals: dict[str, int] = {}
            phase_finished: dict[str, int] = {}
            for r in md_rows:
                ph = r["phase"]
                phase_totals[ph] = phase_totals.get(ph, 0) + 1
                if r["status"] == "finished":
                    phase_finished[ph] = phase_finished.get(ph, 0) + 1

            completed_phases = {
                ph for ph, total in phase_totals.items()
                if total > 0 and phase_finished.get(ph, 0) >= total
            }

            for src_phase, tgt_phase in _AUTO_MARKET_TRANSITIONS:
                if src_phase not in completed_phases:
                    continue

                for lg in leagues_rows:
                    league_id = lg["id"]
                    db = await get_db()
                    try:
                        existing = await db.execute_fetchall(
                            "SELECT id, status, clause_window_start FROM market_windows WHERE league_id=$1 AND phase=$2",
                            (league_id, tgt_phase),
                        )
                    finally:
                        await db.close()

                    now_dt = datetime.now(timezone.utc)
                    clause_start = now_dt
                    clause_end = clause_start + timedelta(days=1)
                    market_start = clause_end
                    market_end = market_start + timedelta(days=1)
                    repo_start = market_end
                    repo_end = repo_start + timedelta(days=1)

                    if existing:
                        win = existing[0]
                        # Already has dates → already activated, nothing to do
                        if win["clause_window_start"]:
                            continue
                        # Pre-created in pending with NULL dates → activate
                        # by filling in the timeline starting now.
                        try:
                            await MarketService.update_market_window(
                                win["id"],
                                {
                                    "clause_window_start": clause_start.isoformat(),
                                    "clause_window_end": clause_end.isoformat(),
                                    "market_window_start": market_start.isoformat(),
                                    "market_window_end": market_end.isoformat(),
                                    "reposition_draft_start": repo_start.isoformat(),
                                    "reposition_draft_end": repo_end.isoformat(),
                                },
                            )
                            print(f"[auto-market] activated window id={win['id']} league={league_id} phase={tgt_phase}")
                        except Exception as e:
                            print(f"[auto-market] error activating window {win['id']}: {e}")
                        continue

                    # Legacy fallback: window doesn't exist at all → create one.
                    try:
                        result = await MarketService.create_market_window(
                            league_id=league_id,
                            phase=tgt_phase,
                            market_type="auto",
                            clause_window_start=clause_start.isoformat(),
                            clause_window_end=clause_end.isoformat(),
                            market_window_start=market_start.isoformat(),
                            market_window_end=market_end.isoformat(),
                            reposition_draft_start=repo_start.isoformat(),
                            reposition_draft_end=repo_end.isoformat(),
                        )
                        # Mark as auto-generated
                        db2 = await get_db()
                        try:
                            await db2.execute(
                                "UPDATE market_windows SET auto_generated=1 WHERE id=$1",
                                (result["id"],),
                            )
                            await db2.commit()
                        finally:
                            await db2.close()
                        print(f"[auto-market] created window id={result['id']} league={league_id} phase={tgt_phase}")
                    except Exception as e:
                        print(f"[auto-market] error creating window for league={league_id} phase={tgt_phase}: {e}")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[auto-market] loop error: {e}")


app = FastAPI(
    title="WC Fantasy 2026",
    description="Fantasy football API for the 2026 FIFA World Cup",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheStaticMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if not path.startswith("/api/"):
            if path.endswith(".html") or path == "/" or "." not in path.split("/")[-1]:
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            else:
                response.headers["Cache-Control"] = "public, max-age=300"
        return response


app.add_middleware(NoCacheStaticMiddleware)

# Include API routers
app.include_router(leagues.router)
app.include_router(players.router)
app.include_router(teams.router)
app.include_router(draft.router)
app.include_router(market.router)
app.include_router(scoring.router)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "app": "wc-fantasy-2026"}


# Serve frontend static files (must be LAST — mount("/") catches everything
# else, so any @app.get() registered after this would be shadowed and return 404)
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
