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
        league = await db.execute_fetchall("SELECT * FROM leagues WHERE id=$1", (league_id,))
        if not league:
            return []
        league = dict(league[0])

        # Count existing teams
        existing = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM fantasy_teams WHERE league_id=$1", (league_id,)
        )
        current_count = existing[0]["cnt"]
        available_slots = league["max_teams"] - current_count
        count = min(count, available_slots)
        if count <= 0:
            return []

        # Get already-used bot names in this league
        used = await db.execute_fetchall(
            "SELECT owner_nick FROM fantasy_teams WHERE league_id=$1 AND owner_nick LIKE 'bot_%'",
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
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
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
            "SELECT ft.id FROM fantasy_teams ft WHERE ft.league_id=$1 AND ft.owner_nick LIKE 'bot_%'",
            (league_id,),
        )
        draft = await db.execute_fetchall(
            "SELECT id FROM drafts WHERE league_id=$1 AND status='in_progress'",
            (league_id,),
        )
        if not draft:
            return
        draft_id = draft[0]["id"]

        for bot in bots:
            bot_id = bot["id"]
            await db.execute(
                """INSERT INTO draft_settings (draft_id, team_id, autodraft, queue)
                   VALUES ($1, $2, 1, '[]')
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
                      COALESCE(p.market_value, 0) AS market_value
               FROM team_players tp JOIN players p ON tp.player_id = p.id
               WHERE tp.team_id=$1""",
            (team_id,),
        )
        if not rows:
            return False

        players = [dict(r) for r in rows]
        by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
        for p in players:
            by_pos.setdefault(p["position"], []).append(p)
        for arr in by_pos.values():
            arr.sort(key=lambda x: x["market_value"], reverse=True)

        chosen = None
        for f in FORMATIONS:
            if all(len(by_pos.get(pos, [])) >= n for pos, n in f.items()):
                picks = []
                for pos, n in f.items():
                    picks.extend(by_pos[pos][:n])
                chosen = picks
                break

        if chosen is None:
            all_sorted = sorted(players, key=lambda x: x["market_value"], reverse=True)
            chosen = all_sorted[:11]

        chosen_ids = {p["player_id"] for p in chosen}
        sorted_starters = sorted(chosen, key=lambda x: x["market_value"], reverse=True)
        captain_id = sorted_starters[0]["player_id"] if sorted_starters else None
        vc_id = sorted_starters[1]["player_id"] if len(sorted_starters) > 1 else None

        await db.execute(
            "UPDATE team_players SET is_starter=0, is_captain=0, is_vice_captain=0 WHERE team_id=$1",
            (team_id,),
        )
        for pid in chosen_ids:
            await db.execute(
                "UPDATE team_players SET is_starter=1 WHERE team_id=$1 AND player_id=$2",
                (team_id, pid),
            )
        if captain_id:
            await db.execute(
                "UPDATE team_players SET is_captain=1 WHERE team_id=$1 AND player_id=$2",
                (team_id, captain_id),
            )
        if vc_id:
            await db.execute(
                "UPDATE team_players SET is_vice_captain=1 WHERE team_id=$1 AND player_id=$2",
                (team_id, vc_id),
            )

        # Propagate to any existing matchday_lineups snapshots so past/active
        # matchdays score correctly when scoring engine prefers matchday_lineups.
        await db.execute(
            "UPDATE matchday_lineups SET is_starter=0, is_captain=0, is_vice_captain=0 WHERE team_id=$1",
            (team_id,),
        )
        if chosen_ids:
            placeholders = ",".join(f"${i+2}" for i in range(len(chosen_ids)))
            await db.execute(
                f"UPDATE matchday_lineups SET is_starter=1 WHERE team_id=$1 AND player_id IN ({placeholders})",
                (team_id, *chosen_ids),
            )
        if captain_id:
            await db.execute(
                "UPDATE matchday_lineups SET is_captain=1 WHERE team_id=$1 AND player_id=$2",
                (team_id, captain_id),
            )
        if vc_id:
            await db.execute(
                "UPDATE matchday_lineups SET is_vice_captain=1 WHERE team_id=$1 AND player_id=$2",
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
            "SELECT id FROM fantasy_teams WHERE league_id=$1 AND owner_nick LIKE 'bot_%'",
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
            "SELECT id FROM fantasy_teams WHERE league_id=$1 AND owner_nick LIKE 'bot_%'",
            (league_id,),
        )
        bot_ids = [b["id"] for b in bots]
        if not bot_ids:
            return 0

        n = len(bot_ids)
        placeholders = ",".join(f"${i+1}" for i in range(n))
        placeholders2 = ",".join(f"${i+1+n}" for i in range(n))
        # Clean up in FK-safe order
        await db.execute(f"DELETE FROM matchday_lineups WHERE team_id IN ({placeholders})", bot_ids)
        await db.execute(f"DELETE FROM team_players WHERE team_id IN ({placeholders})", bot_ids)
        await db.execute(f"DELETE FROM draft_settings WHERE team_id IN ({placeholders})", bot_ids)
        await db.execute(f"DELETE FROM draft_picks WHERE team_id IN ({placeholders})", bot_ids)
        await db.execute(f"DELETE FROM transfers WHERE from_team_id IN ({placeholders}) OR to_team_id IN ({placeholders2})", bot_ids + bot_ids)
        await db.execute(f"DELETE FROM fantasy_teams WHERE id IN ({placeholders})", bot_ids)
        await db.commit()
        logger.info(f"Removed {len(bot_ids)} bots from league {league_id}")
        return len(bot_ids)
    finally:
        await db.close()


# Preset clause amounts (must mirror frontend CLAUSE_PRESETS).
_CLAUSE_PRESETS = [0, 1_000_000, 5_000_000, 15_000_000, 25_000_000, 50_000_000, 80_000_000]


def _snap_to_preset(value: int) -> int:
    """Return the largest preset <= value (min 0)."""
    chosen = 0
    for p in _CLAUSE_PRESETS:
        if p <= value:
            chosen = p
        else:
            break
    return chosen


async def set_bot_clauses_for_window(window_id: int) -> int:
    """Auto-set clauses for every bot team in the league of this market window.

    Strategy per bot:
      - Load roster (player_id, position, market_value, country_code,
        total_points = SUM(match_scores.points), alive = country has any
        non-finished match scheduled).
      - Eliminated-country players → SELL (clause=0, not blocked) → released
        when market opens.
      - Top 2 alive players by priority → blocked (clause=0, is_blocked=True).
        Priority = total_points * 1.5 + market_value/1e7.
      - Remaining alive players → tiered clauses by rank (50M / 25M / 15M / 5M
        / 1M), trimmed to fit within ``protect_budget``.

    Returns count of bots that received clauses.
    """
    from src.backend.database import get_db
    # Late import to avoid circular dependency
    from src.backend.services.market_service import MarketService

    db = await get_db()
    try:
        window = await db.execute_fetchall(
            "SELECT id, league_id, protect_budget FROM market_windows WHERE id=$1",
            (window_id,),
        )
        if not window:
            return 0
        window = dict(window[0])
        league_id = window["league_id"]
        protect_budget = window["protect_budget"] or 300_000_000

        bots = await db.execute_fetchall(
            "SELECT id FROM fantasy_teams WHERE league_id=$1 AND owner_nick LIKE 'bot_%'",
            (league_id,),
        )
        bot_ids = [b["id"] for b in bots]
    finally:
        await db.close()

    if not bot_ids:
        return 0

    processed = 0
    for team_id in bot_ids:
        try:
            await _set_clauses_for_one_bot(team_id, window_id, protect_budget)
            processed += 1
        except Exception as e:
            logger.error(f"Bot clause setup failed for team {team_id}: {e}")

    logger.info(
        f"Bot clauses set for {processed}/{len(bot_ids)} bots in window {window_id}"
    )
    return processed


async def _set_clauses_for_one_bot(team_id: str, window_id: int, protect_budget: int):
    """Compute and persist clauses for a single bot team."""
    from src.backend.database import get_db
    from src.backend.services.market_service import MarketService, get_alive_country_codes

    alive_codes = await get_alive_country_codes()
    db = await get_db()
    try:
        # Roster + total points (alive flag computed in Python from alive_codes).
        roster = await db.execute_fetchall(
            """
            SELECT tp.player_id,
                   p.position,
                   p.country_code,
                   COALESCE(p.market_value, 0) AS market_value,
                   COALESCE((SELECT SUM(ms.total_points) FROM match_scores ms
                             WHERE ms.player_id = tp.player_id), 0) AS total_points
            FROM team_players tp
            JOIN players p ON tp.player_id = p.id
            WHERE tp.team_id = $1
            """,
            (team_id,),
        )
    finally:
        await db.close()

    if not roster:
        return

    players = [dict(r) for r in roster]
    for p in players:
        p["alive"] = (alive_codes is None) or (p["country_code"] in alive_codes)
        # Priority: heavy weight on accumulated points, market_value as tiebreak.
        # Eliminated players are pushed to bottom (negative priority).
        if p["alive"]:
            p["priority"] = float(p["total_points"]) * 1.5 + (p["market_value"] / 1e7)
        else:
            p["priority"] = -1.0  # any alive player ranks above any eliminated one

    players.sort(key=lambda x: x["priority"], reverse=True)

    # Build clause list
    clauses = []
    alive_players = [p for p in players if p["alive"]]
    dead_players = [p for p in players if not p["alive"]]

    # Top 2 alive → blocked
    blocked_ids = {p["player_id"] for p in alive_players[:2]}

    # Tiered targets for remaining alive players (rank-based)
    def target_for_rank(idx: int) -> int:
        if idx < 2:
            return 50_000_000
        if idx < 5:
            return 25_000_000
        if idx < 8:
            return 15_000_000
        if idx < 12:
            return 5_000_000
        return 1_000_000

    # Compute targets for remaining alive
    remaining_alive = [p for p in alive_players if p["player_id"] not in blocked_ids]
    targets = []
    for idx, p in enumerate(remaining_alive):
        targets.append([p, target_for_rank(idx)])

    # Trim to fit protect_budget — drop preset tier on top players first.
    def total_targets():
        return sum(t for _, t in targets)

    while total_targets() > protect_budget and targets:
        # Find the player with the highest target and demote them.
        max_idx = max(range(len(targets)), key=lambda i: targets[i][1])
        cur = targets[max_idx][1]
        # Demote to next lower preset
        try:
            cur_pos = _CLAUSE_PRESETS.index(cur)
        except ValueError:
            cur_pos = 0
        if cur_pos == 0:
            break  # already at 0, can't reduce further
        targets[max_idx][1] = _CLAUSE_PRESETS[cur_pos - 1]

    # Build final clauses list for all roster players.
    target_map = {p["player_id"]: amount for p, amount in targets}
    for p in players:
        pid = p["player_id"]
        if pid in blocked_ids:
            clauses.append({
                "player_id": pid,
                "clause_amount": 0,
                "is_blocked": True,
            })
        elif not p["alive"]:
            # Eliminated → SELL (will be released when market opens)
            clauses.append({
                "player_id": pid,
                "clause_amount": 0,
                "is_blocked": False,
            })
        else:
            clauses.append({
                "player_id": pid,
                "clause_amount": target_map.get(pid, 1_000_000),
                "is_blocked": False,
            })

    await MarketService.set_player_clauses(window_id, team_id, clauses)
    logger.info(
        f"Bot {team_id} clauses set: {len(clauses)} players, "
        f"{len(blocked_ids)} blocked, {len(dead_players)} eliminated→SELL, "
        f"total={sum(c['clause_amount'] for c in clauses if not c['is_blocked'])}"
    )


# Per-window lock so reposition autodraft cascades don't overlap.
_reposition_locks: dict[int, "asyncio.Lock"] = {}


def _get_reposition_lock(window_id: int):
    import asyncio as _asyncio
    lock = _reposition_locks.get(window_id)
    if lock is None:
        lock = _asyncio.Lock()
        _reposition_locks[window_id] = lock
    return lock


async def process_reposition_autodraft(window_id: int, max_iterations: int = 100) -> int:
    """Make picks for any bot whose turn is up in the reposition draft.

    Stops when the next turn is a human or when no turns remain.
    Returns the count of picks performed.
    """
    from src.backend.database import get_db
    from src.backend.services.market_service import MarketService

    lock = _get_reposition_lock(window_id)
    if lock.locked():
        # Another cascade is already running for this window.
        return 0

    picks_made = 0
    async with lock:
        for _ in range(max_iterations):
            db = await get_db()
            try:
                # Window status check
                win_rows = await db.execute_fetchall(
                    "SELECT status, league_id FROM market_windows WHERE id=$1",
                    (window_id,),
                )
                if not win_rows or win_rows[0]["status"] != "reposition_draft":
                    return picks_made
                league_id = win_rows[0]["league_id"]

                # Find current pending pick
                turn_rows = await db.execute_fetchall(
                    """SELECT team_id, pick_number FROM reposition_draft_picks
                       WHERE market_window_id=$1 AND player_id IS NULL AND is_pass=0
                       ORDER BY pick_number LIMIT 1""",
                    (window_id,),
                )
                if not turn_rows:
                    return picks_made
                team_id = turn_rows[0]["team_id"]

                # Is this team a bot?
                bot_rows = await db.execute_fetchall(
                    "SELECT owner_nick FROM fantasy_teams WHERE id=$1", (team_id,)
                )
                if not bot_rows or not bot_rows[0]["owner_nick"].startswith("bot_"):
                    return picks_made  # human's turn, stop cascade
            finally:
                await db.close()

            # Pick the highest market_value alive player not yet owned in league.
            available = await MarketService.get_reposition_available_players(
                league_id=league_id, window_id=window_id
            )
            if not available:
                # Pass the turn — nothing to pick
                logger.info(f"Bot {team_id} has no available players, passing turn")
                await MarketService.make_reposition_draft_pick(
                    window_id=window_id, team_id=team_id, player_id=None
                )
                picks_made += 1
                continue

            # Choose: highest market_value player whose position is below cap.
            db = await get_db()
            try:
                pos_rows = await db.execute_fetchall(
                    """SELECT p.position, COUNT(*) as cnt
                       FROM team_players tp JOIN players p ON tp.player_id=p.id
                       WHERE tp.team_id=$1 GROUP BY p.position""",
                    (team_id,),
                )
                pos_counts = {r["position"]: r["cnt"] for r in pos_rows}
            finally:
                await db.close()

            POS_MAX = {"GK": 3, "DEF": 8, "MID": 8, "FWD": 8}
            chosen = None
            for p in available:
                if pos_counts.get(p["position"], 0) < POS_MAX.get(p["position"], 99):
                    chosen = p
                    break

            if chosen is None:
                # No legal pick for this bot — pass.
                logger.info(f"Bot {team_id} cannot fill any position, passing")
                await MarketService.make_reposition_draft_pick(
                    window_id=window_id, team_id=team_id, player_id=None
                )
            else:
                logger.info(
                    f"Bot {team_id} reposition pick: {chosen['name']} ({chosen['position']})"
                )
                await MarketService.make_reposition_draft_pick(
                    window_id=window_id, team_id=team_id, player_id=chosen["id"]
                )
            picks_made += 1

    return picks_made
