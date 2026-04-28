"""Market service — handle market windows, clauses, transactions, and reposition draft."""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from src.backend.database import get_db

logger = logging.getLogger(__name__)


class MarketService:
    """Service for managing market windows and related operations."""

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
    AUTO_MARKET_PHASES = ["r32", "r16", "quarter", "semi", "final"]

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
        """Transition market window to clause_window phase."""
        db = await get_db()
        try:
            await db.execute(
                "UPDATE market_windows SET status='clause_window', updated_at=$1 WHERE id=$2",
                (datetime.now().isoformat(), window_id),
            )
            await db.commit()
            return await MarketService.get_market_window(window_id)
        except Exception as e:
            logger.error(f"Error starting clause phase: {e}")
            raise
        finally:
            await db.close()

    @staticmethod
    async def start_market_phase(window_id: int) -> Dict[str, Any]:
        """Transition to market_open phase and initialize budgets for all teams."""
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
                    await db.execute(
                        """INSERT INTO market_budgets 
                           (market_window_id, team_id, initial_budget, remaining_budget)
                           VALUES ($1, $2, $3, $4)""",
                        (window_id, team_id, window["initial_budget"], window["initial_budget"]),
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
        """Close market window and prepare for reposition draft."""
        db = await get_db()
        try:
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
        """Set clause values for player list."""
        db = await get_db()
        try:
            # Validate clause count and total budget
            blocked_count = sum(1 for c in clauses if c.get("is_blocked"))
            total_budget = sum(c.get("clause_amount", 0) for c in clauses)

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
            for clause in clauses:
                await db.execute(
                    """INSERT INTO player_clauses 
                       (market_window_id, team_id, player_id, clause_amount, is_blocked, created_at, updated_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)""",
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
        """Get all clauses set by a team for a market window."""
        db = await get_db()
        try:
            clauses = await db.execute_fetchall(
                """SELECT pc.player_id, p.name, pc.clause_amount, pc.is_blocked
                   FROM player_clauses pc
                   JOIN players p ON pc.player_id = p.id
                   WHERE pc.market_window_id=$1 AND pc.team_id=$2""",
                (window_id, team_id),
            )
            return [dict(c) for c in clauses]
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
                       COALESCE(pc.is_blocked, 0) as is_blocked
                FROM team_players tp
                JOIN fantasy_teams ft ON tp.team_id = ft.id
                JOIN players p ON tp.player_id = p.id
                LEFT JOIN player_clauses pc ON pc.player_id = tp.player_id 
                    AND pc.team_id = tp.team_id 
                    AND pc.market_window_id = $1
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
            window = await MarketService.get_market_window(window_id)
            if buyer_budget["buys_count"] >= window["max_buys"]:
                return {"success": False, "reason": f"Max purchases ({window['max_buys']}) reached"}

            # Check seller hasn't exceeded max_sells (robos)
            seller_budget = await MarketService.get_market_budget(window_id, seller_team_id)
            if seller_budget and seller_budget["sells_count"] >= window["max_sells"]:
                return {"success": False, "reason": "Seller reached maximum sells limit"}

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
                   GROUP BY mb.team_id
                   ORDER BY mb.remaining_budget DESC""",
                (window_id,),
            )
            return [dict(o) for o in order]
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
            return {"status": "reposition_draft", "draft_order": order}
        except Exception as e:
            logger.error(f"Error starting reposition draft: {e}")
            raise
        finally:
            await db.close()

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
                   GROUP BY rdp.team_id
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
        """Get available players for reposition draft (players without minutes)."""
        db = await get_db()
        try:
            # Players not currently in any team in this league
            players = await db.execute_fetchall(
                """SELECT p.id, p.name, p.position, p.country_code, p.photo, p.market_value
                   FROM players p
                   WHERE p.id NOT IN (
                       SELECT DISTINCT player_id FROM team_players 
                       WHERE team_id IN (
                           SELECT id FROM fantasy_teams WHERE league_id = $1
                       )
                   )
                   ORDER BY p.market_value DESC""",
                (league_id,),
            )
            return [dict(p) for p in players]
        except Exception as e:
            logger.error(f"Error getting available reposition players: {e}")
            raise
        finally:
            await db.close()

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

            if player_id:
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

                # If team still has <23 players, append a new pick row at end of queue
                count_row = await db.execute_fetchall(
                    "SELECT COUNT(*) as cnt FROM team_players WHERE team_id=$1",
                    (team_id,),
                )
                player_count = count_row[0]["cnt"]

                if player_count < 23:
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
            return {"success": True}
        except Exception as e:
            logger.error(f"Error making reposition draft pick: {e}")
            raise
        finally:
            await db.close()
