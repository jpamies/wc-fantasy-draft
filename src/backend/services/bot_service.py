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


async def set_default_lineup_for_bot(team_id: str) -> bool:
    """Pick 11 starters + captain/VC for a bot team and persist in team_players.

    Tries common formations in order and uses the first one whose position counts
    can be filled by the bot's drafted players (sorted by strength desc).
    Falls back to best-11 by strength if no formation fits.

    The scoring engine falls back to team_players when matchday_lineups doesn't
    exist for a given matchday — so this alone is enough for bots to score.
    """
    from src.backend.database import get_db

    FORMATIONS = [
        {"GK": 1, "DEF": 4, "MID": 3, "FWD": 3},
        {"GK": 1, "DEF": 4, "MID": 4, "FWD": 2},
        {"GK": 1, "DEF": 3, "MID": 4, "FWD": 3},
        {"GK": 1, "DEF": 3, "MID": 5, "FWD": 2},
        {"GK": 1, "DEF": 5, "MID": 3, "FWD": 2},
        {"GK": 1, "DEF": 5, "MID": 4, "FWD": 1},
        {"GK": 1, "DEF": 4, "MID": 5, "FWD": 1},
    ]

    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT tp.player_id, p.position,
                      COALESCE(p.strength, 0) AS strength,
                      COALESCE(p.market_value, 0) AS market_value
               FROM team_players tp JOIN players p ON tp.player_id = p.id
               WHERE tp.team_id=?""",
            (team_id,),
        )
        if not rows:
            return False

        players = [dict(r) for r in rows]
        by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
        for p in players:
            by_pos.setdefault(p["position"], []).append(p)
        for arr in by_pos.values():
            arr.sort(key=lambda x: (x["strength"], x["market_value"]), reverse=True)

        chosen = None
        for f in FORMATIONS:
            if all(len(by_pos.get(pos, [])) >= n for pos, n in f.items()):
                picks = []
                for pos, n in f.items():
                    picks.extend(by_pos[pos][:n])
                chosen = picks
                break

        if chosen is None:
            all_sorted = sorted(players, key=lambda x: (x["strength"], x["market_value"]), reverse=True)
            chosen = all_sorted[:11]

        chosen_ids = {p["player_id"] for p in chosen}
        sorted_starters = sorted(chosen, key=lambda x: (x["strength"], x["market_value"]), reverse=True)
        captain_id = sorted_starters[0]["player_id"] if sorted_starters else None
        vc_id = sorted_starters[1]["player_id"] if len(sorted_starters) > 1 else None

        await db.execute(
            "UPDATE team_players SET is_starter=0, is_captain=0, is_vice_captain=0 WHERE team_id=?",
            (team_id,),
        )
        for pid in chosen_ids:
            await db.execute(
                "UPDATE team_players SET is_starter=1 WHERE team_id=? AND player_id=?",
                (team_id, pid),
            )
        if captain_id:
            await db.execute(
                "UPDATE team_players SET is_captain=1 WHERE team_id=? AND player_id=?",
                (team_id, captain_id),
            )
        if vc_id:
            await db.execute(
                "UPDATE team_players SET is_vice_captain=1 WHERE team_id=? AND player_id=?",
                (team_id, vc_id),
            )
        await db.commit()
        logger.info(f"Bot lineup set for team {team_id}: 11 starters, cap={captain_id}, vc={vc_id}")
        return True
    finally:
        await db.close()


async def auto_lineup_all_bots(league_id: str) -> int:
    """Run set_default_lineup_for_bot for every bot team in the league."""
    from src.backend.database import get_db
    db = await get_db()
    try:
        bots = await db.execute_fetchall(
            "SELECT id FROM fantasy_teams WHERE league_id=? AND owner_nick LIKE 'bot_%'",
            (league_id,),
        )
        bot_ids = [dict(b)["id"] for b in bots]
    finally:
        await db.close()

    count = 0
    for bid in bot_ids:
        if await set_default_lineup_for_bot(bid):
            count += 1
    logger.info(f"Auto-lineup applied to {count}/{len(bot_ids)} bots in league {league_id}")
    return count


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
