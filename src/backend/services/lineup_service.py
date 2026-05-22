"""Lineup service for 5-player matchday lineups and in-game substitutions."""

import logging
from datetime import datetime
from src.backend.database import get_db

logger = logging.getLogger("wc-fantasy.lineup")

LINEUP_STRUCTURE = {"GK": 1, "DEF": 1, "MID": 1, "FWD": 1, "WILDCARD": 1}
LINEUP_SIZE = 5


async def validate_5_player_lineup(team_id: str, lineup_spec: dict) -> tuple[bool, str]:
    """
    Validate a (possibly partial) 5-slot lineup structure:
    {
        'GK': player_id,
        'DEF': player_id,
        'MID': player_id,
        'FWD': player_id,
        'WILDCARD': player_id
    }
    
    Rules:
    1. Cada slot enviado debe tener un jugador del equipo
    2. El wildcard puede ser de cualquier posición
    3. Ningún jugador duplicado entre slots enviados
    4. Los slots normales enviados deben respetar posición (GK=GK, DEF=DEF, etc.)
    """
    db = await get_db()
    try:
        # Fetch team's players
        players = await db.execute_fetchall(
            """SELECT tp.player_id, p.position FROM team_players tp 
               JOIN players p ON tp.player_id = p.id 
               WHERE tp.team_id = $1""",
            (team_id,),
        )
        
        if lineup_spec is None:
            return False, "Lineup payload is required"

        allowed_slots = set(LINEUP_STRUCTURE.keys())
        if any(slot not in allowed_slots for slot in lineup_spec.keys()):
            return False, f"Invalid lineup slot. Allowed: {sorted(allowed_slots)}"
        
        squad_map = {p["player_id"]: p["position"] for p in players}
        player_ids = set(lineup_spec.values())
        
        # Check all players in lineup belong to team
        if not player_ids.issubset(set(squad_map.keys())):
            return False, "Some players not in your squad"
        
        # Check no duplicates among submitted slots
        if len(player_ids) != len(lineup_spec.values()):
            return False, "Duplicate players in lineup"
        
        # Validate position constraints
        for slot, player_id in lineup_spec.items():
            if slot == "WILDCARD":
                continue  # Wildcard can be any position
            
            actual_pos = squad_map[player_id]
            if actual_pos != slot:
                return False, f"Player in {slot} slot must be {slot}, not {actual_pos}"
        
        return True, "OK"
    finally:
        await db.close()


async def ensure_matchday_snapshot(team_id: str, matchday_id: str):
    """Create matchday lineup snapshot from team_players if not exists.
    Called when matchday starts or when user first accesses lineup."""
    db = await get_db()
    try:
        # Check if snapshot already exists
        existing = await db.execute_fetchall(
            "SELECT COUNT(*) as c FROM matchday_lineups WHERE team_id=$1 AND matchday_id=$2",
            (team_id, matchday_id),
        )
        if existing[0]["c"] > 0:
            return  # Already snapshotted
        
        # Ensure matchday row exists for FK integrity
        md_exists = await db.execute_fetchall("SELECT id FROM matchdays WHERE id=$1", (matchday_id,))
        if not md_exists:
            await db.execute(
                "INSERT INTO matchdays (id, name, date, phase, status) VALUES ($1,$2,$3,$4,$5) ON CONFLICT (id) DO NOTHING",
                (matchday_id, matchday_id, "", "groups", "upcoming"),
            )
        
        # Create snapshot from current team_players
        players = await db.execute_fetchall(
            """SELECT player_id, is_starter, is_captain, is_vice_captain 
               FROM team_players WHERE team_id=$1""",
            (team_id,),
        )
        
        for p in players:
            await db.execute(
                """INSERT INTO matchday_lineups
                   (team_id, matchday_id, player_id, is_starter, is_captain, is_vice_captain, is_wildcard, position_slot)
                   VALUES ($1, $2, $3, $4, $5, $6, 0, NULL)""",
                (team_id, matchday_id, p["player_id"],
                 p["is_starter"], p["is_captain"], p["is_vice_captain"]),
            )
        
        await db.commit()
        logger.info(f"Created lineup snapshot for team {team_id} matchday {matchday_id}: {len(players)} players")
    finally:
        await db.close()


async def get_played_countries(matchday_id: str) -> set[str]:
    """Get country codes that have already played in this matchday."""
    from src.backend.config import settings
    
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


async def can_perform_substitution(team_id: str, matchday_id: str, player_out_id: str, player_in_id: str) -> tuple[bool, str]:
    """
    Check if a mid-matchday substitution is allowed.
    
    Rules:
    ✅ player_out must have already played (minutes_played > 0)
    ✅ player_in must NOT have played yet (minutes_played = 0 or no match_scores row)
    ✅ Both players in team's current lineup
    ✅ player_out must be a starter
    ✅ player_in must be on bench
    """
    db = await get_db()
    try:
        # Check matchday is active
        matchday = await db.execute_fetchall(
            "SELECT status FROM matchdays WHERE id=$1",
            (matchday_id,)
        )
        if not matchday or matchday[0]["status"] != "active":
            return False, "Matchday must be active"
        
        # Get current lineup (from matchday_lineups)
        lineup = await db.execute_fetchall(
            "SELECT player_id FROM matchday_lineups WHERE team_id=$1 AND matchday_id=$2",
            (team_id, matchday_id)
        )
        lineup_ids = {p["player_id"] for p in lineup}
        
        if player_out_id not in lineup_ids:
            return False, f"Player {player_out_id} not in current lineup"
        if player_in_id not in lineup_ids:
            return False, f"Player {player_in_id} not in current squad"
        
        # Check player_out is currently a starter
        out_starter = await db.execute_fetchall(
            "SELECT is_starter FROM matchday_lineups WHERE team_id=$1 AND matchday_id=$2 AND player_id=$3",
            (team_id, matchday_id, player_out_id)
        )
        if not out_starter or not out_starter[0]["is_starter"]:
            return False, f"Player {player_out_id} is not a current starter"
        
        # Check player_in is currently on bench
        in_bench = await db.execute_fetchall(
            "SELECT is_starter FROM matchday_lineups WHERE team_id=$1 AND matchday_id=$2 AND player_id=$3",
            (team_id, matchday_id, player_in_id)
        )
        if not in_bench or in_bench[0]["is_starter"]:
            return False, f"Player {player_in_id} must be on bench"
        
        # Check player_out has played (minutes > 0)
        out_score = await db.execute_fetchall(
            "SELECT minutes_played FROM match_scores WHERE player_id=$1 AND matchday_id=$2",
            (player_out_id, matchday_id)
        )
        if not out_score or out_score[0]["minutes_played"] == 0:
            return False, f"Can only sub OUT players who have already played (minutes > 0)"
        
        # Check player_in has NOT played (minutes = 0 or no row)
        in_score = await db.execute_fetchall(
            "SELECT minutes_played FROM match_scores WHERE player_id=$1 AND matchday_id=$2",
            (player_in_id, matchday_id)
        )
        if in_score and in_score[0]["minutes_played"] > 0:
            return False, f"Can only sub IN players who haven't played yet"
        
        return True, "OK"
    finally:
        await db.close()


async def validate_lineup_for_scoring(team_id: str, matchday_id: str) -> tuple[bool, str]:
    """
    Before scoring, check:
    1. Lineup has exactly 5 starters
    2. 4 normales + 1 wildcard
    3. No duplicados
    4. Todos pertenecen al equipo
    """
    db = await get_db()
    try:
        starters = await db.execute_fetchall(
            """SELECT COUNT(*) as cnt, SUM(CASE WHEN is_wildcard=1 THEN 1 ELSE 0 END) as wildcard_count 
               FROM matchday_lineups 
               WHERE team_id=$1 AND matchday_id=$2 AND is_starter=1""",
            (team_id, matchday_id)
        )
        
        if not starters or starters[0]["cnt"] != LINEUP_SIZE:
            return False, f"Invalid lineup: {starters[0]['cnt'] if starters else 0} starters, need {LINEUP_SIZE}"
        if starters[0]["wildcard_count"] != 1:
            return False, "Lineup must have exactly 1 wildcard"
        
        return True, "OK"
    finally:
        await db.close()
