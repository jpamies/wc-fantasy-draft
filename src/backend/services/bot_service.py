"""Bot service — manages AI-controlled fantasy teams.

Bots are regular fantasy_teams with owner_nick starting with 'bot_'.
They auto-draft by default and can be extended with lineup/transfer logic.
"""

import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger("wc-fantasy.bots")

BOT_NAMES = [
    ("Bot Guardiola", "Tiki-Taka FC"),
    ("Bot Mourinho", "Park the Bus United"),
    ("Bot Klopp", "Gegenpressing XI"),
    ("Bot Ancelotti", "Elegancia CF"),
    ("Bot Simeone", "Atlético Bot"),
    ("Bot Bielsa", "Loco's XI"),
    ("Bot Zidane", "Zinedine's Dream"),
    ("Bot Ferguson", "Red Devils Bot"),
    ("Bot Cruyff", "Total Football"),
    ("Bot Sacchi", "Arrigo's Milano"),
]


async def create_bots(league_id: str, count: int) -> list[dict]:
    """Create bot teams in a league. Returns list of created bot info."""
    if count <= 0:
        return []
    if count > 10:
        count = 10

    from src.backend.database import get_db
    db = await get_db()
    try:
        # Get league info
        league = await db.execute_fetchall("SELECT * FROM leagues WHERE id=?", (league_id,))
        if not league:
            return []
        league = dict(league[0])

        # Count existing teams
        existing = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM fantasy_teams WHERE league_id=?", (league_id,)
        )
        current_count = existing[0]["cnt"]
        available_slots = league["max_teams"] - current_count
        count = min(count, available_slots)
        if count <= 0:
            return []

        # Get already-used bot names in this league
        used = await db.execute_fetchall(
            "SELECT owner_nick FROM fantasy_teams WHERE league_id=? AND owner_nick LIKE 'bot_%'",
            (league_id,),
        )
        used_nicks = {r["owner_nick"] for r in used}

        now = datetime.now(timezone.utc).isoformat()
        created = []

        for i in range(len(BOT_NAMES)):
            if len(created) >= count:
                break
            nick, team_name = BOT_NAMES[i]
            bot_nick = f"bot_{nick.lower().replace(' ', '_')}"
            if bot_nick in used_nicks:
                continue

            team_id = f"team-{uuid.uuid4().hex[:8]}"
            await db.execute(
                """INSERT INTO fantasy_teams
                   (id, league_id, owner_nick, display_name, team_name, budget, formation, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (team_id, league_id, bot_nick, nick, team_name,
                 league["initial_budget"], "4-3-3", now),
            )
            created.append({"team_id": team_id, "nick": bot_nick, "name": team_name})
            logger.info(f"Created bot {bot_nick} ({team_name}) in league {league_id}")

        await db.commit()
        return created
    finally:
        await db.close()


async def enable_autodraft_for_bots(league_id: str):
    """Enable autodraft for all bot teams in a league (call after draft starts)."""
    from src.backend.database import get_db
    db = await get_db()
    try:
        bots = await db.execute_fetchall(
            "SELECT ft.id FROM fantasy_teams ft WHERE ft.league_id=? AND ft.owner_nick LIKE 'bot_%'",
            (league_id,),
        )
        draft = await db.execute_fetchall(
            "SELECT id FROM drafts WHERE league_id=? AND status='in_progress'",
            (league_id,),
        )
        if not draft:
            return
        draft_id = draft[0]["id"]

        for bot in bots:
            bot_id = bot["id"]
            await db.execute(
                """INSERT INTO draft_settings (draft_id, team_id, autodraft, queue)
                   VALUES (?, ?, 1, '[]')
                   ON CONFLICT(draft_id, team_id) DO UPDATE SET autodraft=1""",
                (draft_id, bot_id),
            )
        await db.commit()
        logger.info(f"Enabled autodraft for {len(bots)} bots in league {league_id}")
    finally:
        await db.close()


async def remove_bots(league_id: str) -> int:
    """Remove all bot teams from a league. Returns count removed."""
    from src.backend.database import get_db
    db = await get_db()
    try:
        bots = await db.execute_fetchall(
            "SELECT id FROM fantasy_teams WHERE league_id=? AND owner_nick LIKE 'bot_%'",
            (league_id,),
        )
        bot_ids = [b["id"] for b in bots]
        if not bot_ids:
            return 0

        placeholders = ",".join("?" * len(bot_ids))
        # Clean up in FK-safe order
        await db.execute(f"DELETE FROM matchday_lineups WHERE team_id IN ({placeholders})", bot_ids)
        await db.execute(f"DELETE FROM team_players WHERE team_id IN ({placeholders})", bot_ids)
        await db.execute(f"DELETE FROM draft_settings WHERE team_id IN ({placeholders})", bot_ids)
        await db.execute(f"DELETE FROM draft_picks WHERE team_id IN ({placeholders})", bot_ids)
        await db.execute(f"DELETE FROM transfers WHERE from_team_id IN ({placeholders}) OR to_team_id IN ({placeholders})", bot_ids + bot_ids)
        await db.execute(f"DELETE FROM fantasy_teams WHERE id IN ({placeholders})", bot_ids)
        await db.commit()
        logger.info(f"Removed {len(bot_ids)} bots from league {league_id}")
        return len(bot_ids)
    finally:
        await db.close()
