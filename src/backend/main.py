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
    else:
        print("⚠️  No SIMULATOR_API_URL configured.")
        print("   Set SIMULATOR_API_URL to point to wc-simulator for player data.")

    # Start autodraft watchdog: resumes drafts stuck on bot/autodraft turns
    # (e.g. after a pod restart mid-cascade)
    watchdog_task = asyncio.create_task(_autodraft_watchdog())

    yield

    watchdog_task.cancel()
    try:
        await watchdog_task
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
            await asyncio.sleep(15)
            db = await get_db()
            try:
                rows = await db.execute_fetchall(
                    "SELECT league_id FROM drafts WHERE status='in_progress'"
                )
            finally:
                await db.close()
            for row in rows:
                league_id = row["league_id"]
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

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "app": "wc-fantasy-2026"}
