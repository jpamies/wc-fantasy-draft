"""Matchday lineup service — snapshot, swaps, and validation."""

import logging
from src.backend.database import get_db
from src.backend.config import settings

logger = logging.getLogger("wc-fantasy.lineup")


async def _get_played_countries(matchday_id: str) -> set[str]:
    """Get country codes that have already played in this matchday (from simulator)."""
    if not settings.SIMULATOR_API_URL:
        return set()
    
    import httpx
    try:
        async with httpx.AsyncClient(
            base_url=settings.SIMULATOR_API_URL.rstrip("/"),
            timeout=10.0,
        ) as client:
            resp = await client.get(f"/api/v1/matches", params={
                "matchday_id": matchday_id,
                "status": "finished",
            })
            resp.raise_for_status()
            matches = resp.json()
        
        played = set()
        for m in matches:
            if m.get("home_code"):
                played.add(m["home_code"])
            if m.get("away_code"):
                played.add(m["away_code"])
        return played
    except Exception as e:
        logger.error(f"Failed to fetch played countries: {e}")
        return set()


async def is_matchday_started(matchday_id: str) -> bool:
    """A matchday has started if at least one match is finished."""
    played = await _get_played_countries(matchday_id)
    return len(played) > 0


async def ensure_matchday_snapshot(team_id: str, matchday_id: str):
    """Create matchday lineup snapshot from current team_players if not exists.
    Called when matchday starts or when user first accesses lineup."""
    db = await get_db()
    try:
        # Check if snapshot already exists
        existing = await db.execute_fetchall(
            "SELECT COUNT(*) as c FROM matchday_lineups WHERE team_id=? AND matchday_id=?",
            (team_id, matchday_id),
        )
        if existing[0]["c"] > 0:
            return  # Already snapshotted
        
        # Create snapshot from current team_players
        players = await db.execute_fetchall(
            """SELECT player_id, is_starter, is_captain, is_vice_captain
               FROM team_players WHERE team_id=?""",
            (team_id,),
        )
        
        for p in players:
            await db.execute(
                """INSERT OR IGNORE INTO matchday_lineups
                   (team_id, matchday_id, player_id, is_starter, is_captain, is_vice_captain)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (team_id, matchday_id, p["player_id"],
                 p["is_starter"], p["is_captain"], p["is_vice_captain"]),
            )
        
        await db.commit()
        logger.info(f"Created lineup snapshot for team {team_id} matchday {matchday_id}: {len(players)} players")
    finally:
        await db.close()


async def get_lineup_status(team_id: str, matchday_id: str) -> dict:
    """Get current lineup with played/not-played status for each player."""
    played_countries = await _get_played_countries(matchday_id)
    started = len(played_countries) > 0
    
    # Ensure snapshot exists if matchday started
    if started:
        await ensure_matchday_snapshot(team_id, matchday_id)
    
    db = await get_db()
    try:
        # Get lineup (snapshot if exists, otherwise current team)
        lineup = await db.execute_fetchall(
            """SELECT ml.player_id, ml.is_starter, ml.is_captain, ml.is_vice_captain,
                      p.name, p.position, p.country_code, p.photo, p.strength
               FROM matchday_lineups ml
               JOIN players p ON ml.player_id = p.id
               WHERE ml.team_id=? AND ml.matchday_id=?""",
            (team_id, matchday_id),
        )
        
        if not lineup:
            # No snapshot yet, show current team
            lineup = await db.execute_fetchall(
                """SELECT tp.player_id, tp.is_starter, tp.is_captain, tp.is_vice_captain,
                          p.name, p.position, p.country_code, p.photo, p.strength
                   FROM team_players tp
                   JOIN players p ON tp.player_id = p.id
                   WHERE tp.team_id=?""",
                (team_id,),
            )
        
        # Get scores for this matchday
        player_ids = [p["player_id"] for p in lineup]
        scores = {}
        if player_ids:
            placeholders = ",".join("?" * len(player_ids))
            score_rows = await db.execute_fetchall(
                f"SELECT player_id, total_points, minutes_played FROM match_scores WHERE matchday_id=? AND player_id IN ({placeholders})",
                (matchday_id, *player_ids),
            )
            scores = {s["player_id"]: dict(s) for s in score_rows}
        
        players = []
        for p in lineup:
            p = dict(p)
            country_played = p["country_code"] in played_countries
            score = scores.get(p["player_id"])
            p["country_played"] = country_played
            p["points"] = score["total_points"] if score else None
            p["can_bench"] = True  # Can always remove from starters
            p["can_start"] = not country_played  # Can only start if country hasn't played
            players.append(p)
        
        return {
            "matchday_id": matchday_id,
            "started": started,
            "played_countries": sorted(played_countries),
            "players": players,
        }
    finally:
        await db.close()


async def swap_player(team_id: str, matchday_id: str, bench_player_id: str, starter_player_id: str) -> dict:
    """Swap a starter with a bench player during a live matchday.
    
    Rules:
    - Matchday must have started
    - bench_player_id: must be on bench, their country must NOT have played
    - starter_player_id: must be a starter (can have played or not)
    - The starter loses their points, the bench player will score when their country plays
    """
    # Verify matchday started
    played_countries = await _get_played_countries(matchday_id)
    if not played_countries:
        return {"error": "Matchday has not started yet. Set lineup before it starts."}
    
    # Ensure snapshot exists
    await ensure_matchday_snapshot(team_id, matchday_id)
    
    db = await get_db()
    try:
        # Get both players from lineup
        starter = await db.execute_fetchall(
            """SELECT ml.player_id, ml.is_starter, p.country_code, p.name
               FROM matchday_lineups ml JOIN players p ON ml.player_id = p.id
               WHERE ml.team_id=? AND ml.matchday_id=? AND ml.player_id=?""",
            (team_id, matchday_id, starter_player_id),
        )
        bench = await db.execute_fetchall(
            """SELECT ml.player_id, ml.is_starter, p.country_code, p.name
               FROM matchday_lineups ml JOIN players p ON ml.player_id = p.id
               WHERE ml.team_id=? AND ml.matchday_id=? AND ml.player_id=?""",
            (team_id, matchday_id, bench_player_id),
        )
        
        if not starter:
            return {"error": f"Player {starter_player_id} not in your matchday lineup"}
        if not bench:
            return {"error": f"Player {bench_player_id} not in your matchday lineup"}
        
        starter = dict(starter[0])
        bench = dict(bench[0])
        
        # Validate: starter must be a starter
        if not starter["is_starter"]:
            return {"error": f"{starter['name']} is not a starter"}
        
        # Validate: bench player must be on bench
        if bench["is_starter"]:
            return {"error": f"{bench['name']} is already a starter"}
        
        # Validate: bench player's country must NOT have played
        if bench["country_code"] in played_countries:
            return {"error": f"{bench['name']}'s country ({bench['country_code']}) has already played. Cannot promote to starter."}
        
        # Execute swap
        await db.execute(
            "UPDATE matchday_lineups SET is_starter=0, is_captain=0, is_vice_captain=0 WHERE team_id=? AND matchday_id=? AND player_id=?",
            (team_id, matchday_id, starter_player_id),
        )
        await db.execute(
            "UPDATE matchday_lineups SET is_starter=1 WHERE team_id=? AND matchday_id=? AND player_id=?",
            (team_id, matchday_id, bench_player_id),
        )
        await db.commit()
        
        logger.info(f"Swap: team {team_id} md {matchday_id}: {starter['name']} → bench, {bench['name']} → starter")
        
        return {
            "ok": True,
            "benched": {"id": starter_player_id, "name": starter["name"], "country_played": starter["country_code"] in played_countries},
            "started": {"id": bench_player_id, "name": bench["name"]},
        }
    finally:
        await db.close()
