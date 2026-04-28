"""Draft engine — manages the draft state machine, snake order, auto-pick."""
import json
import logging
import random
from datetime import datetime, timezone

from src.backend.database import get_db
from src.backend.config import settings

_use_simulator = bool(settings.SIMULATOR_API_URL)

# Squad composition targets for autodraft
SQUAD_TARGETS = {"GK": (2, 3), "DEF": (5, 8), "MID": (5, 8), "FWD": (5, 8)}  # (min, max)
SQUAD_SIZE = 23


class DraftEngine:

    @staticmethod
    def compute_snake_order(team_ids: list[str], total_rounds: int = 23) -> list[list[str]]:
        """Generate snake draft order: round 1 forward, round 2 reverse, etc."""
        order = []
        for r in range(total_rounds):
            if r % 2 == 0:
                order.append(list(team_ids))
            else:
                order.append(list(reversed(team_ids)))
        return order

    @staticmethod
    async def start_draft(league_id: str) -> dict:
        db = await get_db()
        try:
            league = await db.execute_fetchall("SELECT * FROM leagues WHERE id=$1", (league_id,))
            if not league:
                return {"error": "League not found"}
            league = dict(league[0])

            if league["status"] not in ("setup", "draft_pending"):
                return {"error": f"Cannot start draft in status: {league['status']}"}

            teams = await db.execute_fetchall(
                "SELECT id FROM fantasy_teams WHERE league_id=$1 ORDER BY created_at", (league_id,)
            )
            if len(teams) < 2:
                return {"error": "Need at least 2 teams"}

            team_ids = [t["id"] for t in teams]
            random.shuffle(team_ids)

            import uuid
            draft_id = f"draft-{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc).isoformat()

            # Remove existing draft if any
            await db.execute("DELETE FROM draft_picks WHERE draft_id IN (SELECT id FROM drafts WHERE league_id=$1)", (league_id,))
            await db.execute("DELETE FROM drafts WHERE league_id=$1", (league_id,))

            await db.execute(
                """INSERT INTO drafts (id, league_id, status, current_round, current_pick, pick_order, started_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                (draft_id, league_id, "in_progress", 1, 1, json.dumps(team_ids), now),
            )
            await db.execute("UPDATE leagues SET status='draft_in_progress' WHERE id=$1", (league_id,))
            await db.commit()
            return {"draft_id": draft_id, "pick_order": team_ids}
        finally:
            await db.close()

    @staticmethod
    async def get_draft_state(league_id: str) -> dict | None:
        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT * FROM drafts WHERE league_id=$1", (league_id,))
            if not drafts:
                return None
            draft = dict(drafts[0])
            pick_order = json.loads(draft["pick_order"])

            picks = await db.execute_fetchall(
                """SELECT dp.*, ft.team_name, p.name as player_name,
                          p.position, p.country_code, p.club, p.market_value
                   FROM draft_picks dp
                   JOIN fantasy_teams ft ON dp.team_id=ft.id
                   JOIN players p ON dp.player_id=p.id
                   WHERE dp.draft_id=$1 ORDER BY dp.round, dp.pick""",
                (draft["id"],),
            )

            # Determine current team
            total_teams = len(pick_order)
            current_round = draft["current_round"]
            current_pick = draft["current_pick"]
            snake_order = DraftEngine.compute_snake_order(pick_order, 23)

            current_team_id = None
            current_team_name = None
            if draft["status"] == "in_progress" and current_round <= 23:
                idx = current_pick - 1
                if 0 <= idx < total_teams:
                    current_team_id = snake_order[current_round - 1][idx]
                    # Get team name
                    t = await db.execute_fetchall("SELECT team_name FROM fantasy_teams WHERE id=$1", (current_team_id,))
                    if t:
                        current_team_name = t[0]["team_name"]

            # Count available players
            picked_ids = [p["player_id"] for p in picks]
            if _use_simulator:
                from src.backend.services.simulator_client import fetch_all_squad_players
                all_players = await fetch_all_squad_players()
                picked_set = set(picked_ids)
                available_count = sum(1 for p in all_players if p["id"] not in picked_set)
            elif picked_ids:
                placeholders = ",".join(f"${i+1}" for i in range(len(picked_ids)))
                avail = await db.execute_fetchall(
                    f"SELECT COUNT(*) as cnt FROM players WHERE id NOT IN ({placeholders})", picked_ids
                )
                available_count = avail[0]["cnt"] if avail else 0
            else:
                avail = await db.execute_fetchall("SELECT COUNT(*) as cnt FROM players")
                available_count = avail[0]["cnt"] if avail else 0

            return {
                "id": draft["id"],
                "league_id": league_id,
                "status": draft["status"],
                "current_round": current_round,
                "current_pick": current_pick,
                "pick_order": pick_order,
                "picks": [dict(p) for p in picks],
                "current_team_id": current_team_id,
                "current_team_name": current_team_name,
                "available_count": available_count,
            }
        finally:
            await db.close()

    @staticmethod
    async def make_pick(league_id: str, team_id: str, player_id: str) -> dict:
        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT * FROM drafts WHERE league_id=$1", (league_id,))
            if not drafts:
                return {"error": "No draft found"}
            draft = dict(drafts[0])
            if draft["status"] != "in_progress":
                return {"error": "Draft not in progress"}

            pick_order = json.loads(draft["pick_order"])
            total_teams = len(pick_order)
            snake = DraftEngine.compute_snake_order(pick_order, 23)

            current_round = draft["current_round"]
            current_pick = draft["current_pick"]

            if current_round > 23:
                return {"error": "Draft completed"}

            expected_team = snake[current_round - 1][current_pick - 1]
            if team_id != expected_team:
                return {"error": "Not your turn"}

            # Check player not already picked
            existing = await db.execute_fetchall(
                "SELECT id FROM draft_picks WHERE draft_id=$1 AND player_id=$2", (draft["id"], player_id)
            )
            if existing:
                return {"error": "Player already drafted"}

            # Check player exists (from simulator or local DB)
            if _use_simulator:
                from src.backend.services.simulator_client import ensure_player_in_db
                player_data = await ensure_player_in_db(player_id)
                if not player_data:
                    return {"error": "Player not found"}
                player = await db.execute_fetchall("SELECT * FROM players WHERE id=$1", (player_id,))
                player = dict(player[0])
            else:
                player = await db.execute_fetchall("SELECT * FROM players WHERE id=$1", (player_id,))
                if not player:
                    return {"error": "Player not found"}
                player = dict(player[0])

            # Check position minimums won't be violated (max 23 players total)
            team_players = await db.execute_fetchall(
                "SELECT p.position FROM draft_picks dp JOIN players p ON dp.player_id=p.id WHERE dp.draft_id=$1 AND dp.team_id=$2",
                (draft["id"], team_id),
            )
            current_count = len(team_players)
            if current_count >= 23:
                return {"error": "Team already full"}

            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "INSERT INTO draft_picks (draft_id, round, pick, team_id, player_id, timestamp) VALUES ($1,$2,$3,$4,$5,$6)",
                (draft["id"], current_round, current_pick, team_id, player_id, now),
            )

            # Add to team_players
            await db.execute(
                "INSERT INTO team_players (team_id, player_id, acquired_via, acquired_at) VALUES ($1,$2,$3,$4) ON CONFLICT (team_id, player_id) DO NOTHING",
                (team_id, player_id, "draft", now),
            )

            # Advance pick
            next_pick = current_pick + 1
            next_round = current_round
            if next_pick > total_teams:
                next_pick = 1
                next_round = current_round + 1

            if next_round > 23:
                # Draft complete
                await db.execute(
                    "UPDATE drafts SET status='completed', current_round=$1, current_pick=$2, completed_at=$3 WHERE id=$4",
                    (next_round, next_pick, now, draft["id"]),
                )
                await db.execute("UPDATE leagues SET status='active' WHERE id=$1", (league_id,))
                # Bots never set their own lineup — give them a sane default 11
                # so they actually score on every matchday.
                try:
                    from src.backend.services.bot_service import auto_lineup_all_bots
                    await auto_lineup_all_bots(league_id)
                except Exception as e:
                    logging.getLogger("wc-fantasy.draft").warning(f"Failed to auto-lineup bots after draft completion: {e}")
            else:
                await db.execute(
                    "UPDATE drafts SET current_round=$1, current_pick=$2 WHERE id=$3",
                    (next_round, next_pick, draft["id"]),
                )

            await db.commit()

            # Get team name for response
            t = await db.execute_fetchall("SELECT team_name FROM fantasy_teams WHERE id=$1", (team_id,))

            return {
                "ok": True,
                "round": current_round,
                "pick": current_pick,
                "team_id": team_id,
                "team_name": t[0]["team_name"] if t else "",
                "player_id": player_id,
                "player_name": player["name"],
            }
        finally:
            await db.close()

    @staticmethod
    async def auto_pick(league_id: str, team_id: str, preferences: list[str] | None = None) -> dict:
        """Auto-pick the best available player based on position preferences."""
        if not preferences:
            preferences = ["FWD", "MID", "DEF", "GK"]

        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=$1", (league_id,))
            if not drafts:
                return {"error": "No draft found"}
            draft_id = drafts[0]["id"]

            picked = await db.execute_fetchall("SELECT player_id FROM draft_picks WHERE draft_id=$1", (draft_id,))
            picked_ids = set(p["player_id"] for p in picked)

            squad_pool = None
            for pos in preferences:
                if _use_simulator:
                    if squad_pool is None:
                        from src.backend.services.simulator_client import fetch_all_squad_players
                        squad_pool = await fetch_all_squad_players()
                    candidates = [p for p in squad_pool if p["position"] == pos and p["id"] not in picked_ids]
                    candidates.sort(key=lambda p: (p.get("strength", 0) or 0, p.get("market_value", 0) or 0), reverse=True)
                    if candidates:
                        return await DraftEngine.make_pick(league_id, team_id, candidates[0]["id"])
                else:
                    if picked_ids:
                        placeholders = ",".join(f"${i+2}" for i in range(len(picked_ids)))
                        candidates = await db.execute_fetchall(
                            f"SELECT id FROM players WHERE position=$1 AND id NOT IN ({placeholders}) ORDER BY market_value DESC LIMIT 1",
                            [pos] + list(picked_ids),
                        )
                    else:
                        candidates = await db.execute_fetchall(
                            "SELECT id FROM players WHERE position=$1 ORDER BY market_value DESC LIMIT 1", (pos,)
                        )
                    if candidates:
                        return await DraftEngine.make_pick(league_id, team_id, candidates[0]["id"])

            return {"error": "No players available"}
        finally:
            await db.close()

    @staticmethod
    async def get_available_players(league_id: str, position: str | None = None, search: str | None = None, country: str | None = None) -> list:
        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=$1", (league_id,))
            if not drafts:
                return []
            draft_id = drafts[0]["id"]

            picked = await db.execute_fetchall("SELECT player_id FROM draft_picks WHERE draft_id=$1", (draft_id,))
            picked_ids = set(p["player_id"] for p in picked)

            if _use_simulator:
                from src.backend.services.simulator_client import fetch_all_squad_players
                all_players = await fetch_all_squad_players()
                
                # Filter out already picked
                available = [p for p in all_players if p["id"] not in picked_ids]
                
                # Apply filters
                if position:
                    available = [p for p in available if p["position"] == position]
                if country:
                    available = [p for p in available if p["country_code"] == country]
                if search:
                    term = search.lower()
                    available = [p for p in available if term in p["name"].lower()]
                
                # Sort by OVR (strength) descending, market_value as tiebreaker
                available.sort(key=lambda p: (p.get("strength", 0) or 0, p.get("market_value", 0) or 0), reverse=True)
                return available

            where = []
            params: list = []
            idx = 1
            if picked_ids:
                placeholders = ",".join(f"${i+idx}" for i in range(len(picked_ids)))
                where.append(f"id NOT IN ({placeholders})")
                params.extend(picked_ids); idx += len(picked_ids)
            if position:
                where.append(f"position=${idx}")
                params.append(position); idx += 1
            if search:
                where.append(f"name ILIKE ${idx}")
                params.append(f"%{search}%"); idx += 1

            where_sql = f"WHERE {' AND '.join(where)}" if where else ""
            rows = await db.execute_fetchall(
                f"SELECT * FROM players {where_sql} ORDER BY market_value DESC LIMIT 100", params
            )
            return [dict(r) for r in rows]
        finally:
            await db.close()

    @staticmethod
    async def set_autodraft(league_id: str, team_id: str, enabled: bool):
        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=$1", (league_id,))
            if not drafts:
                return
            draft_id = drafts[0]["id"]
            await db.execute(
                """INSERT INTO draft_settings (draft_id, team_id, autodraft)
                   VALUES ($1, $2, $3)
                   ON CONFLICT(draft_id, team_id) DO UPDATE SET autodraft=excluded.autodraft""",
                (draft_id, team_id, 1 if enabled else 0),
            )
            await db.commit()
        finally:
            await db.close()

    @staticmethod
    async def is_autodraft(league_id: str, team_id: str) -> bool:
        db = await get_db()
        try:
            rows = await db.execute_fetchall(
                """SELECT ds.autodraft FROM draft_settings ds
                   JOIN drafts d ON ds.draft_id = d.id
                   WHERE d.league_id=$1 AND ds.team_id=$2""",
                (league_id, team_id),
            )
            return bool(rows and rows[0]["autodraft"])
        finally:
            await db.close()

    @staticmethod
    async def get_autodraft_teams(league_id: str) -> dict[str, bool]:
        db = await get_db()
        try:
            rows = await db.execute_fetchall(
                """SELECT ds.team_id, ds.autodraft FROM draft_settings ds
                   JOIN drafts d ON ds.draft_id = d.id
                   WHERE d.league_id=$1 AND ds.autodraft=1""",
                (league_id,),
            )
            return {r["team_id"]: True for r in rows}
        finally:
            await db.close()

    @staticmethod
    async def smart_pick(league_id: str, team_id: str) -> dict:
        """Pick the best available player based on squad composition needs.

        Strategy:
        1. Count current squad composition by position
        2. If any position is below its minimum, pick that position (highest value)
        3. If all minimums are met, pick the highest value player in any position
           that hasn't hit its maximum
        """
        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=$1", (league_id,))
            if not drafts:
                return {"error": "No draft found"}
            draft_id = drafts[0]["id"]

            # Count what this team already has by position
            team_picks = await db.execute_fetchall(
                """SELECT p.position, COUNT(*) as cnt
                   FROM draft_picks dp JOIN players p ON dp.player_id=p.id
                   WHERE dp.draft_id=$1 AND dp.team_id=$2
                   GROUP BY p.position""",
                (draft_id, team_id),
            )
            current = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
            for row in team_picks:
                current[row["position"]] = row["cnt"]
            total_picked = sum(current.values())
            remaining = SQUAD_SIZE - total_picked

            if remaining <= 0:
                return {"error": "Team already full"}

            # Get all picked player IDs in this draft
            all_picked = await db.execute_fetchall("SELECT player_id FROM draft_picks WHERE draft_id=$1", (draft_id,))
            picked_ids = [p["player_id"] for p in all_picked]

            # Calculate what positions still need filling
            # First, figure out which positions are below minimum
            needs = []
            for pos, (min_req, _) in SQUAD_TARGETS.items():
                deficit = min_req - current[pos]
                if deficit > 0:
                    needs.append((deficit, pos))

            # Sort by biggest deficit first (ensure we fill critical gaps)
            needs.sort(reverse=True)

            # Also calculate remaining "flex" slots after minimums
            mandatory_remaining = sum(max(0, SQUAD_TARGETS[pos][0] - current[pos]) for pos in SQUAD_TARGETS)
            flex_slots = remaining - mandatory_remaining

            # Build priority order: positions below minimum first, then any non-maxed position
            priority_positions = [pos for _, pos in needs]

            # Add positions that aren't maxed out (for flex picks)
            for pos in ["FWD", "MID", "DEF"]:  # Prefer outfield for flex
                if pos not in priority_positions and current[pos] < SQUAD_TARGETS[pos][1]:
                    priority_positions.append(pos)
            if "GK" not in priority_positions and current["GK"] < SQUAD_TARGETS["GK"][1]:
                priority_positions.append("GK")

            # Try to pick from each priority position
            squad_pool = None
            picked_set = set(picked_ids)
            for pos in priority_positions:
                if _use_simulator:
                    if squad_pool is None:
                        from src.backend.services.simulator_client import fetch_all_squad_players
                        squad_pool = await fetch_all_squad_players()
                    candidates = [p for p in squad_pool if p["position"] == pos and p["id"] not in picked_set]
                    candidates.sort(key=lambda p: (p.get("strength", 0) or 0, p.get("market_value", 0) or 0), reverse=True)
                    if candidates:
                        return await DraftEngine.make_pick(league_id, team_id, candidates[0]["id"])
                else:
                    if picked_ids:
                        placeholders = ",".join(f"${i+2}" for i in range(len(picked_ids)))
                        candidates = await db.execute_fetchall(
                            f"SELECT id FROM players WHERE position=$1 AND id NOT IN ({placeholders}) ORDER BY market_value DESC LIMIT 1",
                            [pos] + picked_ids,
                        )
                    else:
                        candidates = await db.execute_fetchall(
                            "SELECT id FROM players WHERE position=$1 ORDER BY market_value DESC LIMIT 1", (pos,)
                        )
                    if candidates:
                        return await DraftEngine.make_pick(league_id, team_id, candidates[0]["id"])

            return {"error": "No players available"}
        finally:
            await db.close()

    @staticmethod
    async def process_autodraft(league_id: str, max_iterations: int = 1) -> list[dict]:
        """After a pick, check if the next team(s) have autodraft OR queue enabled and pick for them.
        Returns list of auto-picks made (for broadcasting). Defaults to 1 pick per
        call so the caller can interleave delays/broadcasts between picks."""
        results = []

        for _ in range(max_iterations):
            state = await DraftEngine.get_draft_state(league_id)
            if not state or state["status"] != "in_progress":
                break

            current_team = state["current_team_id"]
            if not current_team:
                break

            has_autodraft = await DraftEngine.is_autodraft(league_id, current_team)
            has_queue = await DraftEngine.has_queue(league_id, current_team)

            if not has_autodraft and not has_queue:
                break

            # Queue takes priority over autodraft
            if has_queue:
                result = await DraftEngine.pick_from_queue(league_id, current_team)
            else:
                result = await DraftEngine.smart_pick(league_id, current_team)

            if "error" in result:
                # Don't disable autodraft for bots — they should always keep retrying.
                # For human users, only disable if they had explicit autodraft enabled.
                is_bot = await DraftEngine._is_bot_team(current_team)
                if has_autodraft and not is_bot:
                    await DraftEngine.set_autodraft(league_id, current_team, False)
                import logging
                logging.getLogger("wc-fantasy.draft").warning(
                    f"Autodraft pick failed for team={current_team} (bot={is_bot}): {result.get('error')}"
                )
                break

            result["auto_mode"] = "queue" if has_queue else "autodraft"
            results.append(result)

        return results

    @staticmethod
    async def _is_bot_team(team_id: str) -> bool:
        db = await get_db()
        try:
            rows = await db.execute_fetchall(
                "SELECT owner_nick FROM fantasy_teams WHERE id=$1", (team_id,)
            )
            if not rows:
                return False
            return (rows[0]["owner_nick"] or "").startswith("bot_")
        finally:
            await db.close()

    # --- Draft Queue (Wishlist) methods — persisted in DB ---

    @staticmethod
    async def _get_draft_id(league_id: str, db=None) -> str | None:
        close = False
        if db is None:
            db = await get_db()
            close = True
        try:
            rows = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=$1", (league_id,))
            return rows[0]["id"] if rows else None
        finally:
            if close:
                await db.close()

    @staticmethod
    async def set_queue(league_id: str, team_id: str, player_ids: list[str]):
        db = await get_db()
        try:
            draft_id = await DraftEngine._get_draft_id(league_id, db)
            if not draft_id:
                return
            await db.execute(
                """INSERT INTO draft_settings (draft_id, team_id, queue)
                   VALUES ($1, $2, $3)
                   ON CONFLICT(draft_id, team_id) DO UPDATE SET queue=excluded.queue""",
                (draft_id, team_id, json.dumps(player_ids)),
            )
            await db.commit()
        finally:
            await db.close()

    @staticmethod
    async def get_queue(league_id: str, team_id: str) -> list[str]:
        db = await get_db()
        try:
            rows = await db.execute_fetchall(
                """SELECT ds.queue FROM draft_settings ds
                   JOIN drafts d ON ds.draft_id = d.id
                   WHERE d.league_id=$1 AND ds.team_id=$2""",
                (league_id, team_id),
            )
            if rows and rows[0]["queue"]:
                return json.loads(rows[0]["queue"])
            return []
        finally:
            await db.close()

    @staticmethod
    async def has_queue(league_id: str, team_id: str) -> bool:
        q = await DraftEngine.get_queue(league_id, team_id)
        return len(q) > 0

    @staticmethod
    async def add_to_queue(league_id: str, team_id: str, player_id: str):
        q = await DraftEngine.get_queue(league_id, team_id)
        if player_id not in q:
            q.append(player_id)
            await DraftEngine.set_queue(league_id, team_id, q)

    @staticmethod
    async def remove_from_queue(league_id: str, team_id: str, player_id: str):
        q = await DraftEngine.get_queue(league_id, team_id)
        if player_id in q:
            q.remove(player_id)
            await DraftEngine.set_queue(league_id, team_id, q)

    @staticmethod
    async def move_in_queue(league_id: str, team_id: str, player_id: str, direction: int):
        """Move a player up (-1) or down (+1) in the queue."""
        q = await DraftEngine.get_queue(league_id, team_id)
        if player_id not in q:
            return
        idx = q.index(player_id)
        new_idx = max(0, min(len(q) - 1, idx + direction))
        if idx != new_idx:
            q.pop(idx)
            q.insert(new_idx, player_id)
            await DraftEngine.set_queue(league_id, team_id, q)

    @staticmethod
    async def clear_queue(league_id: str, team_id: str):
        await DraftEngine.set_queue(league_id, team_id, [])

    @staticmethod
    async def pick_from_queue(league_id: str, team_id: str) -> dict:
        """Pick the first available player from this team's queue."""
        q = await DraftEngine.get_queue(league_id, team_id)
        if not q:
            return {"error": "Queue is empty"}

        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=$1", (league_id,))
            if not drafts:
                return {"error": "No draft found"}
            draft_id = drafts[0]["id"]

            picked = await db.execute_fetchall("SELECT player_id FROM draft_picks WHERE draft_id=$1", (draft_id,))
            picked_set = {p["player_id"] for p in picked}

            # Find the first queued player that's still available
            new_q = list(q)
            for player_id in list(q):
                if player_id not in picked_set:
                    new_q.remove(player_id)
                    await DraftEngine.set_queue(league_id, team_id, new_q)
                    return await DraftEngine.make_pick(league_id, team_id, player_id)
                else:
                    new_q.remove(player_id)

            await DraftEngine.set_queue(league_id, team_id, new_q)
            return {"error": "No queued players available"}
        finally:
            await db.close()
