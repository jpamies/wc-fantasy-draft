"""Draft engine — manages the draft state machine, snake order, auto-pick."""
import json
import random
from datetime import datetime, timezone

from src.backend.database import get_db


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
            league = await db.execute_fetchall("SELECT * FROM leagues WHERE id=?", (league_id,))
            if not league:
                return {"error": "League not found"}
            league = dict(league[0])

            if league["status"] not in ("setup", "draft_pending"):
                return {"error": f"Cannot start draft in status: {league['status']}"}

            teams = await db.execute_fetchall(
                "SELECT id FROM fantasy_teams WHERE league_id=? ORDER BY created_at", (league_id,)
            )
            if len(teams) < 2:
                return {"error": "Need at least 2 teams"}

            team_ids = [t["id"] for t in teams]
            random.shuffle(team_ids)

            import uuid
            draft_id = f"draft-{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc).isoformat()

            # Remove existing draft if any
            await db.execute("DELETE FROM draft_picks WHERE draft_id IN (SELECT id FROM drafts WHERE league_id=?)", (league_id,))
            await db.execute("DELETE FROM drafts WHERE league_id=?", (league_id,))

            await db.execute(
                """INSERT INTO drafts (id, league_id, status, current_round, current_pick, pick_order, started_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (draft_id, league_id, "in_progress", 1, 1, json.dumps(team_ids), now),
            )
            await db.execute("UPDATE leagues SET status='draft_in_progress' WHERE id=?", (league_id,))
            await db.commit()
            return {"draft_id": draft_id, "pick_order": team_ids}
        finally:
            await db.close()

    @staticmethod
    async def get_draft_state(league_id: str) -> dict | None:
        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT * FROM drafts WHERE league_id=?", (league_id,))
            if not drafts:
                return None
            draft = dict(drafts[0])
            pick_order = json.loads(draft["pick_order"])

            picks = await db.execute_fetchall(
                """SELECT dp.*, ft.team_name, p.name as player_name
                   FROM draft_picks dp
                   JOIN fantasy_teams ft ON dp.team_id=ft.id
                   JOIN players p ON dp.player_id=p.id
                   WHERE dp.draft_id=? ORDER BY dp.round, dp.pick""",
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
                    t = await db.execute_fetchall("SELECT team_name FROM fantasy_teams WHERE id=?", (current_team_id,))
                    if t:
                        current_team_name = t[0]["team_name"]

            # Count available players
            picked_ids = [p["player_id"] for p in picks]
            if picked_ids:
                placeholders = ",".join("?" for _ in picked_ids)
                avail = await db.execute_fetchall(
                    f"SELECT COUNT(*) as cnt FROM players WHERE id NOT IN ({placeholders})", picked_ids
                )
            else:
                avail = await db.execute_fetchall("SELECT COUNT(*) as cnt FROM players")

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
                "available_count": avail[0]["cnt"] if avail else 0,
            }
        finally:
            await db.close()

    @staticmethod
    async def make_pick(league_id: str, team_id: str, player_id: str) -> dict:
        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT * FROM drafts WHERE league_id=?", (league_id,))
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
                "SELECT id FROM draft_picks WHERE draft_id=? AND player_id=?", (draft["id"], player_id)
            )
            if existing:
                return {"error": "Player already drafted"}

            # Check player exists
            player = await db.execute_fetchall("SELECT * FROM players WHERE id=?", (player_id,))
            if not player:
                return {"error": "Player not found"}
            player = dict(player[0])

            # Check position minimums won't be violated (max 23 players total)
            team_players = await db.execute_fetchall(
                "SELECT p.position FROM draft_picks dp JOIN players p ON dp.player_id=p.id WHERE dp.draft_id=? AND dp.team_id=?",
                (draft["id"], team_id),
            )
            current_count = len(team_players)
            if current_count >= 23:
                return {"error": "Team already full"}

            now = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "INSERT INTO draft_picks (draft_id, round, pick, team_id, player_id, timestamp) VALUES (?,?,?,?,?,?)",
                (draft["id"], current_round, current_pick, team_id, player_id, now),
            )

            # Add to team_players
            await db.execute(
                "INSERT OR IGNORE INTO team_players (team_id, player_id, acquired_via, acquired_at) VALUES (?,?,?,?)",
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
                    "UPDATE drafts SET status='completed', current_round=?, current_pick=?, completed_at=? WHERE id=?",
                    (next_round, next_pick, now, draft["id"]),
                )
                await db.execute("UPDATE leagues SET status='active' WHERE id=?", (league_id,))
            else:
                await db.execute(
                    "UPDATE drafts SET current_round=?, current_pick=? WHERE id=?",
                    (next_round, next_pick, draft["id"]),
                )

            await db.commit()

            # Get team name for response
            t = await db.execute_fetchall("SELECT team_name FROM fantasy_teams WHERE id=?", (team_id,))

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
            drafts = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=?", (league_id,))
            if not drafts:
                return {"error": "No draft found"}
            draft_id = drafts[0]["id"]

            picked = await db.execute_fetchall("SELECT player_id FROM draft_picks WHERE draft_id=?", (draft_id,))
            picked_ids = [p["player_id"] for p in picked]

            for pos in preferences:
                if picked_ids:
                    placeholders = ",".join("?" for _ in picked_ids)
                    candidates = await db.execute_fetchall(
                        f"SELECT id FROM players WHERE position=? AND id NOT IN ({placeholders}) ORDER BY market_value DESC LIMIT 1",
                        [pos] + picked_ids,
                    )
                else:
                    candidates = await db.execute_fetchall(
                        "SELECT id FROM players WHERE position=? ORDER BY market_value DESC LIMIT 1", (pos,)
                    )
                if candidates:
                    return await DraftEngine.make_pick(league_id, team_id, candidates[0]["id"])

            return {"error": "No players available"}
        finally:
            await db.close()

    @staticmethod
    async def get_available_players(league_id: str, position: str | None = None, search: str | None = None) -> list:
        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=?", (league_id,))
            if not drafts:
                return []
            draft_id = drafts[0]["id"]

            picked = await db.execute_fetchall("SELECT player_id FROM draft_picks WHERE draft_id=?", (draft_id,))
            picked_ids = [p["player_id"] for p in picked]

            where = []
            params: list = []
            if picked_ids:
                placeholders = ",".join("?" for _ in picked_ids)
                where.append(f"id NOT IN ({placeholders})")
                params.extend(picked_ids)
            if position:
                where.append("position=?")
                params.append(position)
            if search:
                where.append("name LIKE ?")
                params.append(f"%{search}%")

            where_sql = f"WHERE {' AND '.join(where)}" if where else ""
            rows = await db.execute_fetchall(
                f"SELECT * FROM players {where_sql} ORDER BY market_value DESC LIMIT 100", params
            )
            return [dict(r) for r in rows]
        finally:
            await db.close()
