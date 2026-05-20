"""Market service — handle market windows, clauses, transactions, and reposition draft."""
import logging
import random
from datetime import datetime
from typing import Optional, List, Dict, Any

from src.backend.database import get_db

logger = logging.getLogger(__name__)


async def get_alive_country_codes() -> Optional[set]:
    """Return the set of country codes still in the tournament.

    Reads ``countries.tournament_status`` which is kept up-to-date by
    ``sync_service.sync_country_tournament_status()`` after every score sync.

    Returns ``None`` when the column doesn't exist yet or all countries are
    alive (tournament hasn't started), meaning callers should treat everyone
    as alive.
    """
    db = await get_db()
    try:
        try:
            rows = await db.execute_fetchall(
                "SELECT code, tournament_status FROM countries WHERE tournament_status IS NOT NULL"
            )
        except Exception:
            # Column might not exist yet (migration pending)
            return None
    finally:
        await db.close()

    if not rows:
        return None

    alive = {r["code"] for r in rows if r["tournament_status"] in ("alive", "champion")}
    eliminated = {r["code"] for r in rows if r["tournament_status"] == "eliminated"}

    # If nobody is eliminated yet, return None (all alive)
    if not eliminated:
        return None

    return alive


class MarketService:
    """Service for managing market windows and related operations."""

    @staticmethod
    async def _record_news_event(
        db,
        league_id: str,
        event_type: str,
        title: str,
        body: str = "",
        related_window_id: Optional[int] = None,
        related_team_id: Optional[str] = None,
        related_player_id: Optional[str] = None,
    ) -> None:
        await db.execute(
            """INSERT INTO news_events
               (league_id, event_type, title, body, related_window_id, related_team_id, related_player_id, created_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            (
                league_id,
                event_type,
                title,
                body,
                related_window_id,
                related_team_id,
                related_player_id,
                datetime.now().isoformat(),
            ),
        )

    @staticmethod
    async def _execute_marked_releases(db, window_id: int, league_id: str) -> int:
        """Release SELL players (clause=0 and not blocked) after market phase closes."""
        sell_rows = await db.execute_fetchall(
            """SELECT pc.team_id, pc.player_id, p.name as player_name, ft.team_name
               FROM player_clauses pc
               JOIN fantasy_teams ft ON pc.team_id = ft.id
               JOIN players p ON pc.player_id = p.id
               WHERE pc.market_window_id=$1 AND ft.league_id=$2
                 AND pc.clause_amount = 0 AND pc.is_blocked = 0""",
            (window_id, league_id),
        )

        from src.backend.services.lineup_service import ensure_matchday_snapshot
        started_mds = await db.execute_fetchall(
            "SELECT id FROM matchdays WHERE status IN ('active','completed')"
        )
        league_team_rows = await db.execute_fetchall(
            "SELECT id FROM fantasy_teams WHERE league_id=$1", (league_id,)
        )
        for md_row in started_mds:
            for t_row in league_team_rows:
                try:
                    await ensure_matchday_snapshot(t_row["id"], md_row["id"])
                except Exception as e:
                    logger.warning(
                        f"Snapshot failed for team {t_row['id']} md {md_row['id']}: {e}"
                    )

        released = 0
        for row in sell_rows:
            team_id = row["team_id"]
            player_id = row["player_id"]
            await db.execute(
                "DELETE FROM team_players WHERE team_id=$1 AND player_id=$2",
                (team_id, player_id),
            )
            await db.execute(
                """DELETE FROM matchday_lineups
                   WHERE team_id=$1 AND player_id=$2
                     AND matchday_id IN (
                         SELECT id FROM matchdays WHERE status NOT IN ('active','completed')
                     )""",
                (team_id, player_id),
            )
            await MarketService._record_news_event(
                db,
                league_id=league_id,
                event_type="release",
                title=f"{row['team_name']} libera a {row['player_name']}",
                body="Jugador liberado al cerrar la fase de mercado.",
                related_window_id=window_id,
                related_team_id=team_id,
                related_player_id=player_id,
            )
            released += 1

        return released

    @staticmethod
    async def _resolve_clause_attempts(db, window_id: int, league_id: str, max_per_team: int) -> Dict[str, int]:
        """Resolve pending clause attempts with random order and per-team caps."""
        pending = await db.execute_fetchall(
            """SELECT ca.id, ca.buyer_team_id, ca.expected_seller_team_id, ca.player_id,
                      ca.clause_amount_snapshot,
                      bt.team_name as buyer_team_name,
                      st.team_name as seller_team_name,
                      p.name as player_name
               FROM clause_attempts ca
               JOIN fantasy_teams bt ON bt.id = ca.buyer_team_id
               JOIN fantasy_teams st ON st.id = ca.expected_seller_team_id
               JOIN players p ON p.id = ca.player_id
               WHERE ca.market_window_id=$1 AND ca.league_id=$2 AND ca.status='pending'""",
            (window_id, league_id),
        )

        attempts = [dict(r) for r in pending]
        random.shuffle(attempts)

        buyer_done: dict[str, int] = {}
        seller_done: dict[str, int] = {}
        executed = 0
        failed = 0

        for a in attempts:
            attempt_id = a["id"]
            buyer_team_id = a["buyer_team_id"]
            expected_seller = a["expected_seller_team_id"]
            player_id = a["player_id"]
            failure_reason = None

            if buyer_done.get(buyer_team_id, 0) >= max_per_team:
                failure_reason = "buyer_limit_reached"

            owner_row = await db.execute_fetchall(
                """SELECT tp.team_id
                   FROM team_players tp
                   JOIN fantasy_teams ft ON ft.id = tp.team_id
                   WHERE tp.player_id=$1 AND ft.league_id=$2""",
                (player_id, league_id),
            )

            if not failure_reason and not owner_row:
                failure_reason = "player_not_owned"

            current_seller = owner_row[0]["team_id"] if owner_row else None

            if not failure_reason and current_seller == buyer_team_id:
                failure_reason = "already_owned"
            if not failure_reason and current_seller != expected_seller:
                failure_reason = "player_already_taken"
            if not failure_reason and seller_done.get(current_seller, 0) >= max_per_team:
                failure_reason = "seller_limit_reached"

            clause_row = await db.execute_fetchall(
                """SELECT clause_amount, is_blocked
                   FROM player_clauses
                   WHERE market_window_id=$1 AND team_id=$2 AND player_id=$3""",
                (window_id, current_seller, player_id),
            ) if not failure_reason else []

            if not failure_reason:
                if clause_row and clause_row[0]["is_blocked"]:
                    failure_reason = "blocked"
                else:
                    clause_amount = clause_row[0]["clause_amount"] if clause_row else a["clause_amount_snapshot"]
                    if clause_amount <= 0:
                        failure_reason = "invalid_clause"

            buyer_budget = await db.execute_fetchall(
                "SELECT remaining_budget FROM market_budgets WHERE market_window_id=$1 AND team_id=$2",
                (window_id, buyer_team_id),
            ) if not failure_reason else []

            if not failure_reason and (not buyer_budget or buyer_budget[0]["remaining_budget"] < clause_amount):
                failure_reason = "insufficient_budget"

            if failure_reason:
                await db.execute(
                    "UPDATE clause_attempts SET status='failed', failure_reason=$1, resolved_at=$2 WHERE id=$3",
                    (failure_reason, datetime.now().isoformat(), attempt_id),
                )
                await MarketService._record_news_event(
                    db,
                    league_id=league_id,
                    event_type="clause_failed",
                    title=f"Clausulazo fallido: {a['buyer_team_name']} por {a['player_name']}",
                    body=f"Resultado: {failure_reason}",
                    related_window_id=window_id,
                    related_team_id=buyer_team_id,
                    related_player_id=player_id,
                )
                failed += 1
                continue

            await db.execute(
                "UPDATE team_players SET team_id=$1, acquired_via='clause', acquired_at=$2 WHERE player_id=$3 AND team_id=$4",
                (buyer_team_id, datetime.now().isoformat(), player_id, current_seller),
            )

            await db.execute(
                """UPDATE market_budgets
                   SET spent_on_buys = spent_on_buys + $1,
                       remaining_budget = remaining_budget - $2,
                       buys_count = buys_count + 1,
                       updated_at = $3
                   WHERE market_window_id = $4 AND team_id = $5""",
                (clause_amount, clause_amount, datetime.now().isoformat(), window_id, buyer_team_id),
            )
            await db.execute(
                """UPDATE market_budgets
                   SET earned_from_sales = earned_from_sales + $1,
                       remaining_budget = remaining_budget + $2,
                       sells_count = sells_count + 1,
                       updated_at = $3
                   WHERE market_window_id = $4 AND team_id = $5""",
                (clause_amount, clause_amount, datetime.now().isoformat(), window_id, current_seller),
            )

            tx = await db.execute_fetchall(
                """INSERT INTO market_transactions
                   (market_window_id, buyer_team_id, seller_team_id, player_id, clause_amount_paid, status)
                   VALUES ($1, $2, $3, $4, $5, 'completed')
                   RETURNING id""",
                (window_id, buyer_team_id, current_seller, player_id, clause_amount),
            )
            tx_id = tx[0]["id"]

            await db.execute(
                "UPDATE clause_attempts SET status='executed', market_transaction_id=$1, resolved_at=$2 WHERE id=$3",
                (tx_id, datetime.now().isoformat(), attempt_id),
            )

            buyer_done[buyer_team_id] = buyer_done.get(buyer_team_id, 0) + 1
            seller_done[current_seller] = seller_done.get(current_seller, 0) + 1
            executed += 1

            await MarketService._record_news_event(
                db,
                league_id=league_id,
                event_type="clause_executed",
                title=f"Clausulazo ejecutado: {a['buyer_team_name']} ficha a {a['player_name']}",
                body=f"Importe: {clause_amount}",
                related_window_id=window_id,
                related_team_id=buyer_team_id,
                related_player_id=player_id,
            )

        return {"executed": executed, "failed": failed}

    # ==================== MARKET WINDOWS ====================

    @staticmethod
    async def create_market_window(
        league_id: str,
        phase: str,
        market_type: str,
        clause_window_start: str,
        clause_window_end: str,
        market_window_start: str,
        market_window_end: str,
        reposition_draft_start: str,
        reposition_draft_end: str,
        max_buys: int = 3,
        max_sells: int = 3,
        initial_budget: int = 100000000,
        protect_budget: int = 300000000,
    ) -> Dict[str, Any]:
        """Create a new market window for a league."""
        db = await get_db()
        try:
            now = datetime.now().isoformat()
            row = await db.execute_fetchall(
                """INSERT INTO market_windows 
                   (league_id, phase, market_type, status, clause_window_start, clause_window_end,
                    market_window_start, market_window_end, reposition_draft_start, reposition_draft_end,
                    max_buys, max_sells, initial_budget, protect_budget, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                   RETURNING id""",
                (
                    league_id, phase, market_type, "pending",
                    clause_window_start, clause_window_end,
                    market_window_start, market_window_end,
                    reposition_draft_start, reposition_draft_end,
                    max_buys, max_sells, initial_budget, protect_budget,
                    now, now
                ),
            )
            await db.commit()
            return {"id": row[0]["id"], "status": "pending"}
        except Exception as e:
            logger.error(f"Error creating market window: {e}")
            raise
        finally:
            await db.close()

    @staticmethod
    async def get_market_window(window_id: int) -> Optional[Dict[str, Any]]:
        """Get market window details."""
        db = await get_db()
        try:
            result = await db.execute_fetchall(
                "SELECT * FROM market_windows WHERE id=$1", (window_id,)
            )
            return dict(result[0]) if result else None
        finally:
            await db.close()

    @staticmethod
    async def update_market_window(window_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update market window configuration."""
        db = await get_db()
        try:
            # Check if window has started (clause_window phase or later)
            existing = await MarketService.get_market_window(window_id)
            if existing["status"] != "pending":
                raise ValueError("Cannot edit market window that has already started")

            allowed_fields = [
                "clause_window_start", "clause_window_end",
                "market_window_start", "market_window_end",
                "reposition_draft_start", "reposition_draft_end",
                "max_buys", "max_sells", "initial_budget", "protect_budget"
            ]

            valid_keys = [k for k in updates.keys() if k in allowed_fields]
            set_parts = [f"{k}=${i+1}" for i, k in enumerate(valid_keys)]
            values = [updates[k] for k in valid_keys]
            n = len(values)
            set_clause = ", ".join(set_parts + [f"updated_at=${n+1}"])
            values.append(datetime.now().isoformat())
            values.append(window_id)

            await db.execute(
                f"UPDATE market_windows SET {set_clause} WHERE id=${n+2}",
                values,
            )
            await db.commit()
            return await MarketService.get_market_window(window_id)
        except Exception as e:
            logger.error(f"Error updating market window: {e}")
            raise
        finally:
            await db.close()

    # Phases of the FIFA WC 2026 that get a market window between them.
    # Order matters: each window is created for the phase named here AFTER the
    # previous phase's matchdays have all finished.
    AUTO_MARKET_PHASES = ["r32", "r16", "quarter", "semi"]

    @staticmethod
    async def ensure_league_market_windows(league_id: str) -> int:
        """Pre-create the 5 phase market windows for a league in `pending`
        state with NULL dates. Auto-creator will fill in the dates when each
        previous phase completes. Idempotent — skips phases that already exist.

        Returns the number of windows created.
        """
        db = await get_db()
        try:
            existing = await db.execute_fetchall(
                "SELECT phase FROM market_windows WHERE league_id=$1",
                (league_id,),
            )
            existing_phases = {r["phase"] for r in existing}

            now = datetime.now().isoformat()
            created = 0
            for phase in MarketService.AUTO_MARKET_PHASES:
                if phase in existing_phases:
                    continue
                await db.execute(
                    """INSERT INTO market_windows
                       (league_id, phase, market_type, status,
                        clause_window_start, clause_window_end,
                        market_window_start, market_window_end,
                        reposition_draft_start, reposition_draft_end,
                        max_buys, max_sells, initial_budget, protect_budget,
                        auto_generated, created_at, updated_at)
                       VALUES ($1, $2, $3, 'pending',
                               NULL, NULL, NULL, NULL, NULL, NULL,
                               $4, $5, $6, $7, 1, $8, $8)""",
                    (league_id, phase, "auto", 3, 3, 100000000, 300000000, now),
                )
                created += 1
            if created:
                await db.commit()
                logger.info(f"Pre-created {created} market windows for league {league_id}")
            return created
        except Exception as e:
            logger.error(f"Error ensuring market windows for league {league_id}: {e}")
            raise
        finally:
            await db.close()

    @staticmethod
    async def start_clause_phase(window_id: int) -> Dict[str, Any]:
        """Transition market window to clause_window phase.

        Pre-populates each team's clauses from the previous window so users
        see their old values as defaults and only need to adjust changes.
        """
        db = await get_db()
        try:
            window = await MarketService.get_market_window(window_id)
            league_id = window["league_id"]

            await db.execute(
                "UPDATE market_windows SET status='clause_window', updated_at=$1 WHERE id=$2",
                (datetime.now().isoformat(), window_id),
            )

            # Copy clauses from the most recent previous window in this league
            prev_window = await db.execute_fetchall(
                """SELECT id FROM market_windows
                   WHERE league_id=$1 AND id < $2
                   ORDER BY id DESC LIMIT 1""",
                (league_id, window_id),
            )
            if prev_window:
                prev_id = prev_window[0]["id"]
                # Only copy for teams that don't already have clauses in this window
                teams_with_clauses = await db.execute_fetchall(
                    "SELECT DISTINCT team_id FROM player_clauses WHERE market_window_id=$1",
                    (window_id,),
                )
                teams_already = {r["team_id"] for r in teams_with_clauses}

                prev_clauses = await db.execute_fetchall(
                    """SELECT pc.team_id, pc.player_id, pc.clause_amount, pc.is_blocked
                       FROM player_clauses pc
                       WHERE pc.market_window_id = $1""",
                    (prev_id,),
                )

                now = datetime.now().isoformat()
                for pc in prev_clauses:
                    if pc["team_id"] in teams_already:
                        continue
                    # Only carry over if the player is still on the same team
                    still_owned = await db.execute_fetchall(
                        "SELECT 1 FROM team_players WHERE team_id=$1 AND player_id=$2",
                        (pc["team_id"], pc["player_id"]),
                    )
                    if still_owned:
                        await db.execute(
                            """INSERT INTO player_clauses
                               (market_window_id, team_id, player_id, clause_amount, is_blocked, created_at, updated_at)
                               VALUES ($1, $2, $3, $4, $5, $6, $7)
                               ON CONFLICT DO NOTHING""",
                            (window_id, pc["team_id"], pc["player_id"],
                             pc["clause_amount"], pc["is_blocked"], now, now),
                        )

            await db.commit()
            result = await MarketService.get_market_window(window_id)
        except Exception as e:
            logger.error(f"Error starting clause phase: {e}")
            raise
        finally:
            await db.close()

        # Auto-set clauses for bot teams (fire-and-forget logged on errors).
        try:
            from src.backend.services.bot_service import set_bot_clauses_for_window
            await set_bot_clauses_for_window(window_id)
        except Exception as e:
            logger.error(f"Bot clauses auto-set failed for window {window_id}: {e}")

        return result

    @staticmethod
    async def start_market_phase(window_id: int) -> Dict[str, Any]:
        """Transition to market_open phase and initialize budgets for all teams.

        Also resolves pending clause attempts in random order with per-team
        limits from league settings.
        """
        db = await get_db()
        try:
            window = await MarketService.get_market_window(window_id)
            league_id = window["league_id"]

            # Transition window
            await db.execute(
                "UPDATE market_windows SET status='market_open', updated_at=$1 WHERE id=$2",
                (datetime.now().isoformat(), window_id),
            )

            # Initialize budgets for all teams in league
            # Carry over remaining_budget from the PREVIOUS market window
            # (if any). Only the first window gives the full initial_budget.
            prev_window = await db.execute_fetchall(
                """SELECT id FROM market_windows
                   WHERE league_id=$1 AND id < $2
                   ORDER BY id DESC LIMIT 1""",
                (league_id, window_id),
            )
            prev_window_id = prev_window[0]["id"] if prev_window else None

            teams = await db.execute_fetchall(
                "SELECT id FROM fantasy_teams WHERE league_id=$1", (league_id,)
            )

            for team in teams:
                team_id = team["id"]
                # Check if budget already exists (skip if present)
                existing = await db.execute_fetchall(
                    "SELECT id FROM market_budgets WHERE market_window_id=$1 AND team_id=$2",
                    (window_id, team_id),
                )
                if not existing:
                    # Try to carry over from previous window
                    carried = None
                    if prev_window_id:
                        prev_budget = await db.execute_fetchall(
                            "SELECT remaining_budget FROM market_budgets WHERE market_window_id=$1 AND team_id=$2",
                            (prev_window_id, team_id),
                        )
                        if prev_budget:
                            carried = prev_budget[0]["remaining_budget"]

                    budget_amount = carried if carried is not None else window["initial_budget"]
                    await db.execute(
                        """INSERT INTO market_budgets 
                           (market_window_id, team_id, initial_budget, remaining_budget)
                           VALUES ($1, $2, $3, $4)""",
                        (window_id, team_id, budget_amount, budget_amount),
                    )

            # Execute SELL releases first so freed slots are available for
            # clause attempt resolution and the open-market buying phase.
            released = await MarketService._execute_marked_releases(db, window_id, league_id)
            if released:
                await MarketService._record_news_event(
                    db,
                    league_id=league_id,
                    event_type="release_summary",
                    title="Jugadores liberados al abrir mercado",
                    body=f"Jugadores liberados: {released}",
                    related_window_id=window_id,
                )

            league_cfg = await db.execute_fetchall(
                "SELECT max_clausulazos_per_window FROM leagues WHERE id=$1",
                (league_id,),
            )
            max_clausulazos = league_cfg[0]["max_clausulazos_per_window"] if league_cfg else 2
            clause_result = await MarketService._resolve_clause_attempts(
                db=db,
                window_id=window_id,
                league_id=league_id,
                max_per_team=max_clausulazos,
            )

            await MarketService._record_news_event(
                db,
                league_id=league_id,
                event_type="clause_resolution",
                title=f"Resolución de clausulazos ({window.get('phase', 'mercado')})",
                body=f"Ejecutados: {clause_result['executed']} · Fallidos: {clause_result['failed']}",
                related_window_id=window_id,
            )

            await db.commit()
            return await MarketService.get_market_window(window_id)
        except Exception as e:
            logger.error(f"Error starting market phase: {e}")
            raise
        finally:
            await db.close()

    @staticmethod
    async def close_market(window_id: int) -> Dict[str, Any]:
        """Close market window: resolve pending clause attempts then close."""
        db = await get_db()
        try:
            window = await MarketService.get_market_window(window_id)
            league_id = window["league_id"]

            # Resolve any pending clause attempts submitted during market_open
            league_cfg = await db.execute_fetchall(
                "SELECT max_clausulazos_per_window FROM leagues WHERE id=$1",
                (league_id,),
            )
            max_clausulazos = league_cfg[0]["max_clausulazos_per_window"] if league_cfg else 2
            clause_result = await MarketService._resolve_clause_attempts(
                db=db,
                window_id=window_id,
                league_id=league_id,
                max_per_team=max_clausulazos,
            )
            if clause_result["executed"] + clause_result["failed"] > 0:
                await MarketService._record_news_event(
                    db,
                    league_id=league_id,
                    event_type="clause_resolution",
                    title=f"Resolución de clausulazos al cerrar mercado",
                    body=f"Ejecutados: {clause_result['executed']} · Fallidos: {clause_result['failed']}",
                    related_window_id=window_id,
                )

            await db.execute(
                "UPDATE market_windows SET status='market_closed', updated_at=$1 WHERE id=$2",
                (datetime.now().isoformat(), window_id),
            )
            await db.commit()
            return await MarketService.get_market_window(window_id)
        except Exception as e:
            logger.error(f"Error closing market: {e}")
            raise
        finally:
            await db.close()

    # ==================== PLAYER CLAUSES ====================

    @staticmethod
    async def set_player_clauses(
        window_id: int, team_id: str, clauses: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Set clause values for player list.

        Blocked players don't consume the protect_budget (they're unrobable
        regardless of amount), and their clause_amount is forced to 0 to
        avoid confusion. Players with clause_amount=0 and not blocked are
        flagged for release when the market opens.
        """
        db = await get_db()
        try:
            # De-duplicate by player so repeated submissions or duplicated UI
            # rows do not violate the unique window/team/player constraint.
            unique_clauses = list({c["player_id"]: c for c in clauses}.values())

            # Normalize: blocked players ignore any clause_amount (set to 0).
            for c in unique_clauses:
                if c.get("is_blocked"):
                    c["clause_amount"] = 0

            # Validate clause count and total budget. Blocked players are
            # excluded from the protect_budget computation.
            blocked_count = sum(1 for c in unique_clauses if c.get("is_blocked"))
            total_budget = sum(
                c.get("clause_amount", 0) for c in unique_clauses if not c.get("is_blocked")
            )

            window = await MarketService.get_market_window(window_id)
            if blocked_count > 2:
                raise ValueError("Maximum 2 blocked players allowed")
            if total_budget > window["protect_budget"]:
                raise ValueError(f"Total clause budget exceeds {window['protect_budget']}")

            # Delete existing clauses for this team in this window
            await db.execute(
                "DELETE FROM player_clauses WHERE market_window_id=$1 AND team_id=$2",
                (window_id, team_id),
            )

            # Insert new clauses
            for clause in unique_clauses:
                await db.execute(
                    """INSERT INTO player_clauses 
                       (market_window_id, team_id, player_id, clause_amount, is_blocked, created_at, updated_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)
                       ON CONFLICT (market_window_id, team_id, player_id)
                       DO UPDATE SET clause_amount=EXCLUDED.clause_amount,
                                     is_blocked=EXCLUDED.is_blocked,
                                     updated_at=EXCLUDED.updated_at""",
                    (
                        window_id, team_id, clause["player_id"],
                        clause.get("clause_amount", 0), int(clause.get("is_blocked", False)),
                        datetime.now().isoformat(), datetime.now().isoformat()
                    ),
                )

            await db.commit()
            return {"status": "ok", "total_budget": total_budget, "blocked_count": blocked_count}
        except Exception as e:
            logger.error(f"Error setting player clauses: {e}")
            raise
        finally:
            await db.close()

    @staticmethod
    async def get_team_clauses(window_id: int, team_id: str) -> List[Dict[str, Any]]:
        """Get all clauses set by a team for a market window.

        If no clauses exist for this window yet, falls back to the most recent
        previous window so users see their old values as defaults.
        """
        db = await get_db()
        try:
            clauses = await db.execute_fetchall(
                """SELECT pc.player_id, p.name, pc.clause_amount, pc.is_blocked
                   FROM player_clauses pc
                   JOIN players p ON pc.player_id = p.id
                   WHERE pc.market_window_id=$1 AND pc.team_id=$2""",
                (window_id, team_id),
            )
            if clauses:
                return [dict(c) for c in clauses]

            # No clauses yet — load from previous window (players still owned)
            window = await MarketService.get_market_window(window_id)
            if not window:
                return []
            prev = await db.execute_fetchall(
                """SELECT id FROM market_windows
                   WHERE league_id=$1 AND id < $2
                   ORDER BY id DESC LIMIT 1""",
                (window["league_id"], window_id),
            )
            if not prev:
                return []
            prev_id = prev[0]["id"]
            prev_clauses = await db.execute_fetchall(
                """SELECT pc.player_id, p.name, pc.clause_amount, pc.is_blocked
                   FROM player_clauses pc
                   JOIN players p ON pc.player_id = p.id
                   JOIN team_players tp ON tp.player_id = pc.player_id AND tp.team_id = pc.team_id
                   WHERE pc.market_window_id=$1 AND pc.team_id=$2""",
                (prev_id, team_id),
            )
            return [dict(c) for c in prev_clauses]
        finally:
            await db.close()

    # ==================== MARKET TRANSACTIONS ====================

    @staticmethod
    async def get_market_budget(window_id: int, team_id: str) -> Optional[Dict[str, Any]]:
        """Get current budget for team in market window."""
        db = await get_db()
        try:
            result = await db.execute_fetchall(
                "SELECT * FROM market_budgets WHERE market_window_id=$1 AND team_id=$2",
                (window_id, team_id),
            )
            if result:
                budget = dict(result[0])
                window = await MarketService.get_market_window(window_id)
                budget["max_buys"] = window["max_buys"]
                budget["max_sells"] = window["max_sells"]
                return budget
            return None
        finally:
            await db.close()

    @staticmethod
    async def get_available_players(
        league_id: str, window_id: int, position: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get list of players available for purchase (with their clauses)."""
        db = await get_db()
        try:

            query = """
                SELECT DISTINCT tp.player_id, p.name, p.position, p.country_code, p.photo, p.market_value,
                       tp.team_id as current_team_id, ft.team_name as current_team_name,
                       COALESCE(pc.clause_amount, 0) as clause_amount,
                       COALESCE(pc.is_blocked, 0) as is_blocked,
                       COALESCE(pts.total, 0) as total_points
                FROM team_players tp
                JOIN fantasy_teams ft ON tp.team_id = ft.id
                JOIN players p ON tp.player_id = p.id
                LEFT JOIN player_clauses pc ON pc.player_id = tp.player_id 
                    AND pc.team_id = tp.team_id 
                    AND pc.market_window_id = $1
                LEFT JOIN (
                    SELECT player_id, SUM(total_points) as total
                    FROM match_scores GROUP BY player_id
                ) pts ON pts.player_id = tp.player_id
                WHERE ft.league_id = $2
            """

            params = [window_id, league_id]

            if position:
                query += " AND p.position = $3"
                params.append(position)

            query += " ORDER BY p.market_value DESC"

            players = await db.execute_fetchall(query, params)
            return [dict(p) for p in players]
        finally:
            await db.close()

    @staticmethod
    async def buy_player(
        window_id: int, buyer_team_id: str, player_id: str
    ) -> Dict[str, Any]:
        """Execute player purchase transaction."""
        db = await get_db()
        try:
            window = await MarketService.get_market_window(window_id)
            if not window:
                return {"success": False, "reason": "Market window not found"}
            if window["status"] in ("clause_window", "market_open"):
                return await MarketService.submit_clause_attempt(window_id, buyer_team_id, player_id)
            if window["status"] not in ("clause_window", "market_open"):
                return {"success": False, "reason": "Market is not open"}

            # Get player's current owner and clause
            owner_result = await db.execute_fetchall(
                """SELECT tp.team_id
                   FROM team_players tp
                   WHERE tp.player_id = $1""",
                (player_id,),
            )

            if not owner_result:
                return {"success": False, "reason": "Player not found"}

            seller_team_id = owner_result[0]["team_id"]

            league_row = await db.execute_fetchall(
                "SELECT league_id FROM fantasy_teams WHERE id=$1",
                (buyer_team_id,),
            )
            league_id = league_row[0]["league_id"] if league_row else None

            if seller_team_id == buyer_team_id:
                return {"success": False, "reason": "Cannot buy own player"}

            # Get clause amount
            clause_result = await db.execute_fetchall(
                """SELECT clause_amount, is_blocked
                   FROM player_clauses
                   WHERE market_window_id = $1 AND team_id = $2 AND player_id = $3""",
                (window_id, seller_team_id, player_id),
            )

            clause_amount = clause_result[0]["clause_amount"] if clause_result else 0
            is_blocked = clause_result[0]["is_blocked"] if clause_result else 0

            if is_blocked:
                return {"success": False, "reason": "Player is blocked"}

            # Check buyer budget
            buyer_budget = await MarketService.get_market_budget(window_id, buyer_team_id)
            if not buyer_budget or buyer_budget["remaining_budget"] < clause_amount:
                return {"success": False, "reason": "Insufficient budget"}

            # Check buyer hasn't exceeded max_buys
            if buyer_budget["buys_count"] >= window["max_buys"]:
                return {"success": False, "reason": f"Max purchases ({window['max_buys']}) reached"}

            # Check seller hasn't exceeded max_sells (robos)
            seller_budget = await MarketService.get_market_budget(window_id, seller_team_id)
            if seller_budget and seller_budget["sells_count"] >= window["max_sells"]:
                return {"success": False, "reason": "Seller reached maximum sells limit"}

            # Check buyer's squad hasn't reached the size/position limits.
            # Total max 12 (5 starters, 7 bench)
            counts_rows = await db.execute_fetchall(
                """SELECT COUNT(*)::int as cnt FROM team_players WHERE team_id=$1""",
                (buyer_team_id,),
            )
            total = counts_rows[0]["cnt"] if counts_rows else 0
            if total >= 12:
                return {"success": False, "reason": "Squad full (12 players)"}
            player_pos_row = await db.execute_fetchall(
                "SELECT position FROM players WHERE id=$1", (player_id,)
            )
            player_pos = player_pos_row[0]["position"] if player_pos_row else None
            if player_pos and counts.get(player_pos, 0) >= POSITION_MAX.get(player_pos, 99):
                return {"success": False, "reason": f"Already at position cap ({POSITION_MAX[player_pos]} {player_pos})"}

            # Use transaction to ensure atomicity
            try:
                # Move player
                await db.execute(
                    "UPDATE team_players SET team_id = $1 WHERE player_id = $2 AND team_id = $3",
                    (buyer_team_id, player_id, seller_team_id),
                )

                # Update budgets
                await db.execute(
                    """UPDATE market_budgets 
                       SET spent_on_buys = spent_on_buys + $1,
                           remaining_budget = remaining_budget - $2,
                           buys_count = buys_count + 1,
                           updated_at = $3
                       WHERE market_window_id = $4 AND team_id = $5""",
                    (clause_amount, clause_amount, datetime.now().isoformat(), window_id, buyer_team_id),
                )

                await db.execute(
                    """UPDATE market_budgets 
                       SET earned_from_sales = earned_from_sales + $1,
                           remaining_budget = remaining_budget + $2,
                           sells_count = sells_count + 1,
                           updated_at = $3
                       WHERE market_window_id = $4 AND team_id = $5""",
                    (clause_amount, clause_amount, datetime.now().isoformat(), window_id, seller_team_id),
                )

                # Record transaction
                tx_row = await db.execute_fetchall(
                    """INSERT INTO market_transactions
                       (market_window_id, buyer_team_id, seller_team_id, player_id, clause_amount_paid, status)
                       VALUES ($1, $2, $3, $4, $5, $6)
                       RETURNING id""",
                    (window_id, buyer_team_id, seller_team_id, player_id, clause_amount, "completed"),
                )
                tx_id = tx_row[0]["id"]

                buyer_team_name = await db.execute_fetchall("SELECT team_name FROM fantasy_teams WHERE id=$1", (buyer_team_id,))
                seller_team_name = await db.execute_fetchall("SELECT team_name FROM fantasy_teams WHERE id=$1", (seller_team_id,))
                player_name = await db.execute_fetchall("SELECT name FROM players WHERE id=$1", (player_id,))
                if league_id:
                    await MarketService._record_news_event(
                        db,
                        league_id=league_id,
                        event_type="market_transfer",
                        title=f"{buyer_team_name[0]['team_name']} ficha a {player_name[0]['name']}",
                        body=f"Desde {seller_team_name[0]['team_name']} por {clause_amount}",
                        related_window_id=window_id,
                        related_team_id=buyer_team_id,
                        related_player_id=player_id,
                    )

                await db.commit()
            except Exception as tx_err:
                await db.rollback()
                logger.error(f"Transaction error: {tx_err}")
                raise

            return {"success": True, "transaction_id": tx_id, "clause_amount_paid": clause_amount}
        except Exception as e:
            logger.error(f"Error buying player: {e}")
            raise
        finally:
            await db.close()

    @staticmethod
    async def submit_clause_attempt(
        window_id: int,
        buyer_team_id: str,
        player_id: str,
    ) -> Dict[str, Any]:
        """Submit a deferred clause attempt during clause window."""
        db = await get_db()
        try:
            window = await MarketService.get_market_window(window_id)
            if not window:
                return {"success": False, "reason": "Market window not found"}
            if window["status"] not in ("clause_window", "market_open"):
                return {"success": False, "reason": "Clause window is closed"}

            league_id = window["league_id"]

            # Enforce clausulazo limit in both clause_window and market_open
            league_rows = await db.execute_fetchall(
                "SELECT max_clausulazos_per_window FROM leagues WHERE id=$1",
                (league_id,),
            )
            max_clausulazos = league_rows[0]["max_clausulazos_per_window"] if league_rows else 2
            submitted_count = await db.execute_fetchall(
                "SELECT COUNT(*)::int as cnt FROM clause_attempts WHERE market_window_id=$1 AND buyer_team_id=$2",
                (window_id, buyer_team_id),
            )
            if submitted_count and submitted_count[0]["cnt"] >= max_clausulazos:
                return {"success": False, "reason": f"Max clausulazos reached ({max_clausulazos})"}

            # Check buyer squad size (cannot bid if already full).
            squad_rows = await db.execute_fetchall(
                "SELECT COUNT(*)::int as cnt FROM team_players WHERE team_id=$1",
                (buyer_team_id,),
            )
            if squad_rows and squad_rows[0]["cnt"] >= 12:
                return {"success": False, "reason": "Squad full (12 players)"}

            owner = await db.execute_fetchall(
                """SELECT tp.team_id, ft.team_name
                   FROM team_players tp
                   JOIN fantasy_teams ft ON ft.id = tp.team_id
                   WHERE tp.player_id=$1 AND ft.league_id=$2""",
                (player_id, league_id),
            )
            if not owner:
                return {"success": False, "reason": "Player not owned in this league"}

            seller_team_id = owner[0]["team_id"]
            if seller_team_id == buyer_team_id:
                return {"success": False, "reason": "Cannot clause your own player"}

            clause = await db.execute_fetchall(
                """SELECT clause_amount, is_blocked
                   FROM player_clauses
                   WHERE market_window_id=$1 AND team_id=$2 AND player_id=$3""",
                (window_id, seller_team_id, player_id),
            )
            clause_amount = clause[0]["clause_amount"] if clause else 0
            is_blocked = clause[0]["is_blocked"] if clause else 0

            if is_blocked:
                return {"success": False, "reason": "Player is blocked"}
            if clause_amount <= 0:
                return {"success": False, "reason": "Player has no valid clause"}

            # Enforce budget: amount of all pending attempts + this one must fit.
            budget_row = await db.execute_fetchall(
                "SELECT remaining_budget FROM market_budgets WHERE market_window_id=$1 AND team_id=$2",
                (window_id, buyer_team_id),
            )
            remaining_budget = budget_row[0]["remaining_budget"] if budget_row else 0
            pending_row = await db.execute_fetchall(
                """SELECT COALESCE(SUM(clause_amount_snapshot),0)::int as total
                   FROM clause_attempts
                   WHERE market_window_id=$1 AND buyer_team_id=$2 AND status='pending'""",
                (window_id, buyer_team_id),
            )
            pending_amount = pending_row[0]["total"] if pending_row else 0
            if clause_amount + pending_amount > remaining_budget:
                return {"success": False, "reason": "Insufficient budget for this clause attempt"}

            try:
                row = await db.execute_fetchall(
                    """INSERT INTO clause_attempts
                       (market_window_id, league_id, buyer_team_id, expected_seller_team_id, player_id, clause_amount_snapshot, status, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7)
                       RETURNING id""",
                    (window_id, league_id, buyer_team_id, seller_team_id, player_id, clause_amount, datetime.now().isoformat()),
                )
            except Exception:
                return {"success": False, "reason": "Attempt already submitted for this player"}

            buyer_name = await db.execute_fetchall("SELECT team_name FROM fantasy_teams WHERE id=$1", (buyer_team_id,))
            player_name = await db.execute_fetchall("SELECT name FROM players WHERE id=$1", (player_id,))
            await MarketService._record_news_event(
                db,
                league_id=league_id,
                event_type="clause_attempt",
                title=f"{buyer_name[0]['team_name']} lanza clausulazo por {player_name[0]['name']}",
                body=f"Importe marcado: {clause_amount}",
                related_window_id=window_id,
                related_team_id=buyer_team_id,
                related_player_id=player_id,
            )

            await db.commit()
            return {
                "success": True,
                "attempt_id": row[0]["id"],
                "status": "pending",
                "clause_amount": clause_amount,
            }
        except Exception as e:
            logger.error(f"Error submitting clause attempt: {e}")
            raise
        finally:
            await db.close()

    @staticmethod
    async def get_clause_attempts(window_id: int, team_id: str) -> List[Dict[str, Any]]:
        db = await get_db()
        try:
            rows = await db.execute_fetchall(
                """SELECT ca.id, ca.player_id, p.name as player_name,
                          ca.expected_seller_team_id, st.team_name as seller_team_name,
                          ca.clause_amount_snapshot, ca.status, ca.failure_reason,
                          ca.created_at, ca.resolved_at
                   FROM clause_attempts ca
                   JOIN players p ON p.id = ca.player_id
                   JOIN fantasy_teams st ON st.id = ca.expected_seller_team_id
                   WHERE ca.market_window_id=$1 AND ca.buyer_team_id=$2
                   ORDER BY ca.created_at DESC""",
                (window_id, team_id),
            )
            return [dict(r) for r in rows]
        finally:
            await db.close()

    @staticmethod
    async def get_clause_log(window_id: int, league_id: str) -> List[Dict[str, Any]]:
        db = await get_db()
        try:
            rows = await db.execute_fetchall(
                """SELECT ca.id, ca.player_id, p.name as player_name,
                          ca.buyer_team_id, bt.team_name as buyer_team_name,
                          ca.expected_seller_team_id as seller_team_id,
                          st.team_name as seller_team_name,
                          ca.clause_amount_snapshot, ca.status, ca.failure_reason,
                          ca.created_at, ca.resolved_at
                   FROM clause_attempts ca
                   JOIN players p ON p.id = ca.player_id
                   JOIN fantasy_teams bt ON bt.id = ca.buyer_team_id
                   JOIN fantasy_teams st ON st.id = ca.expected_seller_team_id
                   WHERE ca.market_window_id=$1 AND ca.league_id=$2
                   ORDER BY ca.created_at DESC""",
                (window_id, league_id),
            )
            return [dict(r) for r in rows]
        finally:
            await db.close()

    @staticmethod
    async def get_transaction_history(window_id: int, team_id: str) -> List[Dict[str, Any]]:
        """Get transaction history for a team in a market window."""
        db = await get_db()
        try:
            transactions = await db.execute_fetchall(
                """SELECT mt.id, mt.buyer_team_id, bt.team_name as buyer_team_name,
                          mt.seller_team_id, st.team_name as seller_team_name,
                          mt.player_id, p.name as player_name,
                          mt.clause_amount_paid, mt.transaction_date,
                          CASE WHEN mt.buyer_team_id = $1 THEN 'bought' ELSE 'sold' END as direction
                   FROM market_transactions mt
                   JOIN fantasy_teams bt ON mt.buyer_team_id = bt.id
                   JOIN fantasy_teams st ON mt.seller_team_id = st.id
                   JOIN players p ON mt.player_id = p.id
                   WHERE mt.market_window_id = $2 
                     AND (mt.buyer_team_id = $3 OR mt.seller_team_id = $4)
                   ORDER BY mt.transaction_date DESC""",
                (team_id, window_id, team_id, team_id),
            )
            return [dict(t) for t in transactions]
        finally:
            await db.close()

    # ==================== REPOSITION DRAFT ====================

    @staticmethod
    async def calculate_reposition_draft_order(window_id: int) -> List[Dict[str, Any]]:
        """Calculate draft order for reposition (descending by remaining budget)."""
        db = await get_db()
        try:
            order = await db.execute_fetchall(
                """SELECT mb.team_id, ft.team_name, ft.owner_nick, mb.remaining_budget,
                          COUNT(tp.player_id) as players_count
                   FROM market_budgets mb
                   JOIN fantasy_teams ft ON mb.team_id = ft.id
                   LEFT JOIN team_players tp ON mb.team_id = tp.team_id
                   WHERE mb.market_window_id = $1
                   GROUP BY mb.team_id, ft.team_name, ft.owner_nick, mb.remaining_budget
                   ORDER BY mb.remaining_budget DESC""",
                (window_id,),
            )
            # Teams already at 12 do not participate in reposition draft.
            return [dict(o) for o in order if (o.get("players_count") or 0) < 12]
        except Exception as e:
            logger.error(f"Error calculating reposition draft order: {e}")
            raise
        finally:
            await db.close()

    @staticmethod
    async def start_reposition_draft(window_id: int) -> Dict[str, Any]:
        """Start reposition draft and generate draft order."""
        db = await get_db()
        try:
            # Calculate order
            order = await MarketService.calculate_reposition_draft_order(window_id)

            # Create draft picks entries (with pick_number set, but empty player_id)
            for pick_num, entry in enumerate(order, 1):
                await db.execute(
                    """INSERT INTO reposition_draft_picks
                       (market_window_id, team_id, pick_number, is_pass)
                       VALUES ($1, $2, $3, 0)""",
                    (window_id, entry["team_id"], pick_num),
                )

            # Update window status
            await db.execute(
                "UPDATE market_windows SET status='reposition_draft', updated_at=$1 WHERE id=$2",
                (datetime.now().isoformat(), window_id),
            )

            await db.commit()
            result = {"status": "reposition_draft", "draft_order": order}
        except Exception as e:
            logger.error(f"Error starting reposition draft: {e}")
            raise
        finally:
            await db.close()

        # Fire-and-forget bot autodraft cascade
        try:
            import asyncio
            from src.backend.services.bot_service import process_reposition_autodraft
            asyncio.create_task(process_reposition_autodraft(window_id))
        except Exception as e:
            logger.error(f"Failed to schedule reposition autodraft: {e}")

        return result

    @staticmethod
    async def get_reposition_draft_state(window_id: int, team_id: str) -> Dict[str, Any]:
        """Get current state of reposition draft for a team."""
        db = await get_db()
        try:
            window = await MarketService.get_market_window(window_id)

            # Get draft order with current status
            order = await db.execute_fetchall(
                """SELECT rdp.team_id, ft.team_name, ft.owner_nick, mb.remaining_budget,
                          COUNT(DISTINCT tp.player_id) as players_count,
                          SUM(CASE WHEN p.position='GK' THEN 1 ELSE 0 END) as gk_count,
                          SUM(CASE WHEN p.position='DEF' THEN 1 ELSE 0 END) as def_count,
                          SUM(CASE WHEN p.position='MID' THEN 1 ELSE 0 END) as mid_count,
                          SUM(CASE WHEN p.position='FWD' THEN 1 ELSE 0 END) as fwd_count,
                          rdp.pick_number
                   FROM reposition_draft_picks rdp
                   JOIN fantasy_teams ft ON rdp.team_id = ft.id
                   LEFT JOIN market_budgets mb ON rdp.market_window_id = mb.market_window_id AND rdp.team_id = mb.team_id
                   LEFT JOIN team_players tp ON rdp.team_id = tp.team_id
                   LEFT JOIN players p ON tp.player_id = p.id
                   WHERE rdp.market_window_id = $1
                   GROUP BY rdp.team_id, ft.team_name, ft.owner_nick, mb.remaining_budget, rdp.pick_number
                   ORDER BY rdp.pick_number""",
                (window_id,),
            )

            # Find current turn (first team with is_pass=0 and player_id is NULL)
            current_turn = await db.execute_fetchall(
                """SELECT team_id, pick_number FROM reposition_draft_picks
                   WHERE market_window_id = $1 AND player_id IS NULL AND is_pass = 0
                   ORDER BY pick_number LIMIT 1""",
                (window_id,),
            )

            current_team_id = current_turn[0]["team_id"] if current_turn else None
            current_turn_num = current_turn[0]["pick_number"] if current_turn else 0

            my_picks = await db.execute_fetchall(
                """SELECT rdp.pick_number, rdp.player_id, p.name, p.position
                   FROM reposition_draft_picks rdp
                   LEFT JOIN players p ON rdp.player_id = p.id
                   WHERE rdp.market_window_id = $1 AND rdp.team_id = $2
                   ORDER BY rdp.pick_number""",
                (window_id, team_id),
            )

            # Count remaining available players (without minutes in this tournament phase)
            # For now, assume all players without significant minutes
            available = await db.execute_fetchall(
                """SELECT COUNT(DISTINCT p.id) as cnt FROM players p
                   WHERE p.id NOT IN (
                       SELECT DISTINCT player_id FROM team_players 
                       WHERE team_id IN (SELECT id FROM fantasy_teams WHERE league_id = $1)
                   )""",
                (window["league_id"],),
            )

            status = "completed" if not current_turn else ("your_turn" if current_team_id == team_id else "waiting_turn")

            return {
                "status": status,
                "current_turn_team_id": current_team_id,
                "current_turn_number": current_turn_num,
                "draft_order": [dict(o) for o in order],
                "remaining_available_players": available[0]["cnt"] if available else 0,
                "my_picks": [dict(p) for p in my_picks],
                "leaderboard": [dict(o) for o in order],
            }
        except Exception as e:
            logger.error(f"Error getting reposition draft state: {e}")
            raise
        finally:
            await db.close()

    @staticmethod
    async def get_reposition_available_players(
        league_id: str, window_id: int
    ) -> List[Dict[str, Any]]:
        """Get available players for reposition draft.

        Returns players that:
          - are not currently in any team of this league, AND
          - belong to a country still alive in the tournament (qualified for
            the next round, not eliminated).

        Uses the simulator as the primary data source so photos, market
        values and club info are always present. Each player is enriched
        with ``total_points`` from match_scores.

        Country status comes from ``countries.tournament_status`` which is
        kept up-to-date by ``sync_country_tournament_status()``.
        """
        from src.backend.config import settings

        db = await get_db()
        try:
            # 1. Owned players in this league.
            owned_rows = await db.execute_fetchall(
                """SELECT DISTINCT player_id FROM team_players
                   WHERE team_id IN (SELECT id FROM fantasy_teams WHERE league_id = $1)""",
                (league_id,),
            )
            owned_ids = {r["player_id"] for r in owned_rows}

            # 2. Alive country set (uses countries.tournament_status synced
            #    by sync_country_tournament_status — accurate across all phases).
            alive_codes = await get_alive_country_codes()

            # 3. Total points per player (from match_scores).
            score_rows = await db.execute_fetchall(
                """SELECT player_id, COALESCE(SUM(total_points), 0) AS pts
                   FROM match_scores GROUP BY player_id"""
            )
            points_by_id = {r["player_id"]: r["pts"] for r in score_rows}
        finally:
            await db.close()

        # 4. Player catalogue — prefer simulator (full data: photo, market_value, strength).
        catalogue: List[Dict[str, Any]] = []
        if settings.SIMULATOR_API_URL:
            try:
                from src.backend.services.simulator_client import fetch_all_squad_players
                catalogue = await fetch_all_squad_players()
            except Exception as e:
                logger.warning(f"Simulator unavailable for reposition pool: {e}")

        if not catalogue:
            # Fallback to local DB.
            db = await get_db()
            try:
                rows = await db.execute_fetchall(
                    """SELECT id, name, position, country_code, photo, market_value, club, club_logo
                       FROM players ORDER BY market_value DESC"""
                )
                catalogue = [dict(r) for r in rows]
            finally:
                await db.close()

        result = []
        for p in catalogue:
            pid = p.get("id")
            if not pid or pid in owned_ids:
                continue
            if alive_codes is not None and p.get("country_code") not in alive_codes:
                continue
            entry = dict(p)
            entry["total_points"] = points_by_id.get(pid, 0)
            result.append(entry)

        # Highest market value first; tiebreak by total_points.
        result.sort(
            key=lambda x: (x.get("market_value") or 0, x.get("total_points") or 0),
            reverse=True,
        )
        return result

    @staticmethod
    async def make_reposition_draft_pick(
        window_id: int, team_id: str, player_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Make a pick in reposition draft (or pass)."""
        db = await get_db()
        try:
            # Check it's this team's turn
            current_turn = await db.execute_fetchall(
                """SELECT team_id, pick_number FROM reposition_draft_picks
                   WHERE market_window_id = $1 AND player_id IS NULL AND is_pass = 0
                   ORDER BY pick_number LIMIT 1""",
                (window_id,),
            )

            if not current_turn or current_turn[0]["team_id"] != team_id:
                return {"success": False, "reason": "Not your turn"}

            pick_number = current_turn[0]["pick_number"]

            # Hard-stop full squads from picking (defense in depth).
            count_row = await db.execute_fetchall(
                "SELECT COUNT(*)::int as cnt FROM team_players WHERE team_id=$1",
                (team_id,),
            )
            if count_row and count_row[0]["cnt"] >= 12:
                await db.execute(
                    "UPDATE reposition_draft_picks SET is_pass=1 WHERE market_window_id=$1 AND team_id=$2 AND pick_number=$3",
                    (window_id, team_id, pick_number),
                )
                await db.commit()
                return {"success": False, "reason": "Squad full (12 players)"}

            if player_id:
                # Ensure full player data is in local DB (the row may be a stub
                # created by score sync without photo/club/detailed_position).
                try:
                    from src.backend.config import settings
                    if settings.SIMULATOR_API_URL:
                        from src.backend.services.simulator_client import ensure_player_in_db
                        await ensure_player_in_db(player_id)
                except Exception as e:
                    logger.warning(f"ensure_player_in_db({player_id}) failed: {e}")

                # Validate player exists and is available
                player = await db.execute_fetchall(
                    "SELECT id, position FROM players WHERE id=$1", (player_id,)
                )
                if not player:
                    return {"success": False, "reason": "Player not found"}

                # Verify player is not already on a team in this league
                window = await MarketService.get_market_window(window_id)
                already = await db.execute_fetchall(
                    """SELECT tp.id FROM team_players tp
                       JOIN fantasy_teams ft ON tp.team_id = ft.id
                       WHERE tp.player_id = $1 AND ft.league_id = $2""",
                    (player_id, window["league_id"]),
                )
                if already:
                    return {"success": False, "reason": "Player already owned in this league"}

                # Update pick
                await db.execute(
                    "UPDATE reposition_draft_picks SET player_id=$1 WHERE market_window_id=$2 AND team_id=$3 AND pick_number=$4",
                    (player_id, window_id, team_id, pick_number),
                )

                # Move player to team
                existing = await db.execute_fetchall(
                    "SELECT id FROM team_players WHERE team_id=$1 AND player_id=$2",
                    (team_id, player_id),
                )
                if not existing:
                    await db.execute(
                        """INSERT INTO team_players (team_id, player_id, acquired_via, acquired_at, market_window_acquired)
                           VALUES ($1, $2, $3, $4, $5)""",
                        (team_id, player_id, "free_market", datetime.now().isoformat(), window_id),
                    )

                # If team still has <12 players, append a new pick row at end of queue
                count_row = await db.execute_fetchall(
                    "SELECT COUNT(*) as cnt FROM team_players WHERE team_id=$1",
                    (team_id,),
                )
                player_count = count_row[0]["cnt"]

                if player_count < 12:
                    # Find max pick_number to append
                    max_row = await db.execute_fetchall(
                        "SELECT MAX(pick_number) as mx FROM reposition_draft_picks WHERE market_window_id=$1",
                        (window_id,),
                    )
                    next_num = (max_row[0]["mx"] or 0) + 1
                    await db.execute(
                        """INSERT INTO reposition_draft_picks
                           (market_window_id, team_id, pick_number, is_pass)
                           VALUES ($1, $2, $3, 0)""",
                        (window_id, team_id, next_num),
                    )
            else:
                # Pass turn — team is out of the draft
                await db.execute(
                    "UPDATE reposition_draft_picks SET is_pass=1 WHERE market_window_id=$1 AND team_id=$2 AND pick_number=$3",
                    (window_id, team_id, pick_number),
                )

            await db.commit()
            result = {"success": True}
        except Exception as e:
            logger.error(f"Error making reposition draft pick: {e}")
            raise
        finally:
            await db.close()

        # If the next pending turn is a bot, fire-and-forget cascade.
        try:
            import asyncio
            from src.backend.services.bot_service import process_reposition_autodraft
            asyncio.create_task(process_reposition_autodraft(window_id))
        except Exception as e:
            logger.error(f"Failed to schedule reposition autodraft: {e}")

        return result
