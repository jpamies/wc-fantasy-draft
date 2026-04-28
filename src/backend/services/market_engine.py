"""Market engine — clausulazos, offers, bids, releases."""
import uuid
from datetime import datetime, timezone

from src.backend.database import get_db


class MarketEngine:

    @staticmethod
    async def execute_clause(league_id: str, buyer_team_id: str, player_id: str) -> dict:
        db = await get_db()
        try:
            # Check window open
            lg = await db.execute_fetchall("SELECT * FROM leagues WHERE id=$1", (league_id,))
            if not lg or not lg[0]["transfer_window_open"]:
                return {"error": "Transfer window is closed"}

            # Check player exists and is owned by someone in this league
            owner = await db.execute_fetchall(
                """SELECT tp.team_id, ft.league_id, p.clause_value, p.name, p.market_value
                   FROM team_players tp
                   JOIN fantasy_teams ft ON tp.team_id=ft.id
                   JOIN players p ON tp.player_id=p.id
                   WHERE tp.player_id=$1 AND ft.league_id=$2""",
                (player_id, league_id),
            )
            if not owner:
                return {"error": "Player not owned by any team in this league"}
            owner = dict(owner[0])
            seller_team_id = owner["team_id"]

            if seller_team_id == buyer_team_id:
                return {"error": "Cannot clause your own player"}

            clause_value = owner["clause_value"]

            # Check buyer budget
            buyer = await db.execute_fetchall("SELECT budget FROM fantasy_teams WHERE id=$1", (buyer_team_id,))
            if not buyer or buyer[0]["budget"] < clause_value:
                return {"error": "Insufficient budget"}

            # Check max clausulazos per window
            max_clauses = lg[0]["max_clausulazos_per_window"]
            used = await db.execute_fetchall(
                """SELECT COUNT(*) as cnt FROM transfers
                   WHERE league_id=$1 AND to_team_id=$2 AND type='clause' AND status='completed'""",
                (league_id, buyer_team_id),
            )
            if used[0]["cnt"] >= max_clauses:
                return {"error": f"Max {max_clauses} clausulazos per window reached"}

            # Check player wasn't already clausulado this window
            already = await db.execute_fetchall(
                "SELECT id FROM transfers WHERE league_id=$1 AND player_id=$2 AND type='clause' AND status='completed'",
                (league_id, player_id),
            )
            if already:
                return {"error": "Player already clausulado this window"}

            now = datetime.now(timezone.utc).isoformat()
            transfer_id = f"xfer-{uuid.uuid4().hex[:8]}"

            # Execute transfer
            await db.execute("DELETE FROM team_players WHERE team_id=$1 AND player_id=$2", (seller_team_id, player_id))
            await db.execute(
                "INSERT INTO team_players (team_id, player_id, acquired_via, acquired_at) VALUES ($1,$2,$3,$4) ON CONFLICT (team_id, player_id) DO NOTHING",
                (buyer_team_id, player_id, "clause", now),
            )
            await db.execute("UPDATE fantasy_teams SET budget=budget-$1 WHERE id=$2", (clause_value, buyer_team_id))
            await db.execute("UPDATE fantasy_teams SET budget=budget+$1 WHERE id=$2", (clause_value, seller_team_id))

            await db.execute(
                """INSERT INTO transfers (id, league_id, type, from_team_id, to_team_id, player_id, amount, status, created_at, resolved_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                (transfer_id, league_id, "clause", seller_team_id, buyer_team_id, player_id, clause_value, "completed", now, now),
            )
            await db.commit()
            return {"ok": True, "transfer_id": transfer_id, "player_name": owner["name"], "amount": clause_value}
        finally:
            await db.close()

    @staticmethod
    async def create_offer(league_id: str, from_team_id: str, to_team_id: str,
                           players_offered: list[str], players_requested: list[str], amount: int) -> dict:
        db = await get_db()
        try:
            lg = await db.execute_fetchall("SELECT transfer_window_open FROM leagues WHERE id=$1", (league_id,))
            if not lg or not lg[0]["transfer_window_open"]:
                return {"error": "Transfer window is closed"}

            now = datetime.now(timezone.utc).isoformat()
            offer_id = f"xfer-{uuid.uuid4().hex[:8]}"
            import json
            await db.execute(
                """INSERT INTO transfers (id, league_id, type, from_team_id, to_team_id, player_id,
                   players_offered, amount, status, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                (offer_id, league_id, "offer", from_team_id, to_team_id,
                 players_requested[0] if players_requested else "",
                 json.dumps({"offered": players_offered, "requested": players_requested}),
                 amount, "pending", now),
            )
            await db.commit()
            return {"ok": True, "offer_id": offer_id}
        finally:
            await db.close()

    @staticmethod
    async def respond_offer(offer_id: str, team_id: str, action: str) -> dict:
        db = await get_db()
        try:
            rows = await db.execute_fetchall("SELECT * FROM transfers WHERE id=$1", (offer_id,))
            if not rows:
                return {"error": "Offer not found"}
            offer = dict(rows[0])
            if offer["to_team_id"] != team_id:
                return {"error": "Not your offer to respond to"}
            if offer["status"] != "pending":
                return {"error": "Offer already resolved"}

            now = datetime.now(timezone.utc).isoformat()

            if action == "accept":
                import json
                details = json.loads(offer["players_offered"]) if offer["players_offered"] else {}
                requested = details.get("requested", [])
                offered = details.get("offered", [])

                # Move requested players from to_team to from_team
                for pid in requested:
                    await db.execute("DELETE FROM team_players WHERE team_id=$1 AND player_id=$2", (offer["to_team_id"], pid))
                    await db.execute(
                        "INSERT INTO team_players (team_id, player_id, acquired_via, acquired_at) VALUES ($1,$2,$3,$4) ON CONFLICT (team_id, player_id) DO NOTHING",
                        (offer["from_team_id"], pid, "transfer", now),
                    )
                # Move offered players from from_team to to_team
                for pid in offered:
                    await db.execute("DELETE FROM team_players WHERE team_id=$1 AND player_id=$2", (offer["from_team_id"], pid))
                    await db.execute(
                        "INSERT INTO team_players (team_id, player_id, acquired_via, acquired_at) VALUES ($1,$2,$3,$4) ON CONFLICT (team_id, player_id) DO NOTHING",
                        (offer["to_team_id"], pid, "transfer", now),
                    )
                # Transfer money
                if offer["amount"] > 0:
                    await db.execute("UPDATE fantasy_teams SET budget=budget-$1 WHERE id=$2", (offer["amount"], offer["from_team_id"]))
                    await db.execute("UPDATE fantasy_teams SET budget=budget+$1 WHERE id=$2", (offer["amount"], offer["to_team_id"]))

                await db.execute("UPDATE transfers SET status='completed', resolved_at=$1 WHERE id=$2", (now, offer_id))
            elif action == "reject":
                await db.execute("UPDATE transfers SET status='rejected', resolved_at=$1 WHERE id=$2", (now, offer_id))
            else:
                return {"error": "Invalid action (accept or reject)"}

            await db.commit()
            return {"ok": True, "status": action + "ed"}
        finally:
            await db.close()

    @staticmethod
    async def release_player(league_id: str, team_id: str, player_id: str) -> dict:
        db = await get_db()
        try:
            # Verify ownership
            tp = await db.execute_fetchall(
                "SELECT tp.*, p.market_value, p.name FROM team_players tp JOIN players p ON tp.player_id=p.id WHERE tp.team_id=$1 AND tp.player_id=$2",
                (team_id, player_id),
            )
            if not tp:
                return {"error": "Player not in your team"}
            refund = tp[0]["market_value"] // 2

            now = datetime.now(timezone.utc).isoformat()
            await db.execute("DELETE FROM team_players WHERE team_id=$1 AND player_id=$2", (team_id, player_id))
            await db.execute("UPDATE fantasy_teams SET budget=budget+$1 WHERE id=$2", (refund, team_id))

            xfer_id = f"xfer-{uuid.uuid4().hex[:8]}"
            await db.execute(
                """INSERT INTO transfers (id, league_id, type, from_team_id, player_id, amount, status, created_at, resolved_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
                (xfer_id, league_id, "release", team_id, player_id, refund, "completed", now, now),
            )
            await db.commit()
            return {"ok": True, "refund": refund, "player_name": tp[0]["name"]}
        finally:
            await db.close()

    @staticmethod
    async def bid_free_agent(league_id: str, team_id: str, player_id: str, amount: int) -> dict:
        db = await get_db()
        try:
            lg = await db.execute_fetchall("SELECT transfer_window_open FROM leagues WHERE id=$1", (league_id,))
            if not lg or not lg[0]["transfer_window_open"]:
                return {"error": "Transfer window is closed"}

            # Check player is free (not on any team in this league)
            owned = await db.execute_fetchall(
                """SELECT tp.team_id FROM team_players tp
                   JOIN fantasy_teams ft ON tp.team_id=ft.id
                   WHERE tp.player_id=$1 AND ft.league_id=$2""",
                (player_id, league_id),
            )
            if owned:
                return {"error": "Player is not a free agent"}

            buyer = await db.execute_fetchall("SELECT budget FROM fantasy_teams WHERE id=$1", (team_id,))
            if not buyer or buyer[0]["budget"] < amount:
                return {"error": "Insufficient budget"}

            now = datetime.now(timezone.utc).isoformat()
            bid_id = f"xfer-{uuid.uuid4().hex[:8]}"
            await db.execute(
                """INSERT INTO transfers (id, league_id, type, to_team_id, player_id, amount, status, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                (bid_id, league_id, "free_market", team_id, player_id, amount, "pending", now),
            )
            await db.commit()
            return {"ok": True, "bid_id": bid_id}
        finally:
            await db.close()

    @staticmethod
    async def resolve_bids(league_id: str) -> list[dict]:
        """Resolve all pending free agent bids — highest bid wins."""
        db = await get_db()
        try:
            pending = await db.execute_fetchall(
                "SELECT * FROM transfers WHERE league_id=$1 AND type='free_market' AND status='pending' ORDER BY player_id, amount DESC",
                (league_id,),
            )
            now = datetime.now(timezone.utc).isoformat()
            resolved = []
            seen_players: set[str] = set()

            for bid in pending:
                bid = dict(bid)
                if bid["player_id"] in seen_players:
                    await db.execute("UPDATE transfers SET status='rejected', resolved_at=$1 WHERE id=$2", (now, bid["id"]))
                    continue

                seen_players.add(bid["player_id"])
                team_id = bid["to_team_id"]

                # Check budget still sufficient
                buyer = await db.execute_fetchall("SELECT budget FROM fantasy_teams WHERE id=$1", (team_id,))
                if buyer and buyer[0]["budget"] >= bid["amount"]:
                    # Ensure player exists in local DB (for FK integrity when using simulator)
                    from src.backend.config import settings
                    if settings.SIMULATOR_API_URL:
                        from src.backend.services.simulator_client import ensure_player_in_db
                        await ensure_player_in_db(bid["player_id"])
                    await db.execute(
                        "INSERT INTO team_players (team_id, player_id, acquired_via, acquired_at) VALUES ($1,$2,$3,$4) ON CONFLICT (team_id, player_id) DO NOTHING",
                        (team_id, bid["player_id"], "free_market", now),
                    )
                    await db.execute("UPDATE fantasy_teams SET budget=budget-$1 WHERE id=$2", (bid["amount"], team_id))
                    await db.execute("UPDATE transfers SET status='completed', resolved_at=$1 WHERE id=$2", (now, bid["id"]))
                    resolved.append(bid)
                else:
                    await db.execute("UPDATE transfers SET status='rejected', resolved_at=$1 WHERE id=$2", (now, bid["id"]))

            await db.commit()
            return resolved
        finally:
            await db.close()

    @staticmethod
    async def get_free_agents(league_id: str) -> list[dict]:
        db = await get_db()
        try:
            owned = await db.execute_fetchall(
                """SELECT DISTINCT tp.player_id FROM team_players tp
                   JOIN fantasy_teams ft ON tp.team_id=ft.id WHERE ft.league_id=$1""",
                (league_id,),
            )
            owned_ids = set(r["player_id"] for r in owned)

            from src.backend.config import settings
            if settings.SIMULATOR_API_URL:
                from src.backend.services.simulator_client import fetch_all_squad_players
                players = await fetch_all_squad_players()
                free = [p for p in players if p["id"] not in owned_ids]
                free.sort(key=lambda p: p.get("market_value", 0) or 0, reverse=True)
                return free[:100]

            if owned_ids:
                placeholders = ",".join(f"${i+1}" for i in range(len(owned_ids)))
                rows = await db.execute_fetchall(
                    f"SELECT * FROM players WHERE id NOT IN ({placeholders}) ORDER BY market_value DESC LIMIT 100",
                    list(owned_ids),
                )
            else:
                rows = await db.execute_fetchall("SELECT * FROM players ORDER BY market_value DESC LIMIT 100")
            return [dict(r) for r in rows]
        finally:
            await db.close()
