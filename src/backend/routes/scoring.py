import logging
from fastapi import APIRouter, HTTPException, Depends
from src.backend.auth import get_current_team
from src.backend.database import get_db
from src.backend.services.scoring_engine import ScoringEngine

logger = logging.getLogger("wc-fantasy.scoring")
router = APIRouter(prefix="/api/v1", tags=["scoring"])


async def _fetch_sim_calendar() -> list[dict]:
    """Fetch calendar from simulator, return empty list on failure."""
    try:
        from src.backend.services.simulator_client import fetch_calendar
        return await fetch_calendar()
    except Exception as e:
        logger.error(f"Failed to fetch calendar from simulator: {e}")
        return []


@router.get("/scoring/matchdays")
async def list_matchdays():
    """List matchdays from simulator, enriched with local status (active/completed)."""
    calendar = await _fetch_sim_calendar()
    if not calendar:
        return []

    # Get local matchday statuses (active/completed from sync)
    db = await get_db()
    try:
        local_mds = await db.execute_fetchall("SELECT id, status FROM matchdays")
        status_map = {r["id"]: r["status"] for r in local_mds}
    finally:
        await db.close()

    result = []
    for md in calendar:
        # Local status overrides simulator status (sync sets active/completed)
        local_status = status_map.get(md["id"])
        sim_status = md.get("status", "scheduled")
        matches = md.get("matches", [])
        some_finished = any(m.get("status") == "finished" for m in matches)
        all_finished = matches and all(m.get("status") == "finished" for m in matches)

        if all_finished:
            md_status = "completed"
        elif local_status:
            md_status = local_status
        elif some_finished:
            md_status = "active"
        else:
            md_status = "upcoming"  # map simulator's "scheduled" → "upcoming"

        result.append({
            "id": md["id"],
            "name": md.get("name", md["id"]),
            "date": md.get("date", ""),
            "phase": md.get("phase", "groups"),
            "status": md_status,
            "match_count": len(matches),
            "finished_count": sum(1 for m in matches if m.get("status") == "finished"),
        })
    return result


@router.get("/scoring/matchdays/{matchday_id}")
async def get_matchday(matchday_id: str):
    """Get matchday detail: matches from simulator, scores from local DB."""
    calendar = await _fetch_sim_calendar()
    md_data = next((md for md in calendar if md["id"] == matchday_id), None)
    if not md_data:
        raise HTTPException(404, "Matchday not found in simulator")

    # Map simulator matches to frontend format
    sim_matches = md_data.get("matches", [])
    matches = []
    for m in sim_matches:
        matches.append({
            "id": m["id"],
            "matchday_id": matchday_id,
            "home_country": m.get("home_code", ""),
            "away_country": m.get("away_code", ""),
            "home_name": m.get("home_team", m.get("home_code", "")),
            "away_name": m.get("away_team", m.get("away_code", "")),
            "home_flag": m.get("home_flag", ""),
            "away_flag": m.get("away_flag", ""),
            "kickoff": m.get("kickoff", ""),
            "score_home": m.get("score_home"),
            "score_away": m.get("score_away"),
            "status": m.get("status", "scheduled"),
        })

    # Get local scores
    db = await get_db()
    try:
        scores = await db.execute_fetchall(
            """SELECT ms.*, p.name as player_name, p.position, p.country_code
               FROM match_scores ms JOIN players p ON ms.player_id=p.id
               WHERE ms.matchday_id=$1 ORDER BY ms.total_points DESC""",
            (matchday_id,),
        )
        local_md = await db.execute_fetchall("SELECT status FROM matchdays WHERE id=$1", (matchday_id,))
    finally:
        await db.close()

    md_status = local_md[0]["status"] if local_md else md_data.get("status", "upcoming")

    return {
        "id": matchday_id,
        "name": md_data.get("name", matchday_id),
        "date": md_data.get("date", ""),
        "phase": md_data.get("phase", "groups"),
        "status": md_status,
        "matches": matches,
        "scores": [dict(s) for s in scores],
    }


@router.get("/scoring/matchdays/{matchday_id}/fantasy-points")
async def get_fantasy_points(matchday_id: str, auth: dict = Depends(get_current_team)):
    """Get all fantasy teams' points for a specific matchday."""
    from src.backend.services.scoring_engine import ScoringEngine
    league_id = auth["league_id"]
    db = await get_db()
    try:
        teams = await db.execute_fetchall(
            "SELECT id, team_name, owner_nick, display_name FROM fantasy_teams WHERE league_id=$1",
            (league_id,),
        )
        results = []
        for t in teams:
            t = dict(t)
            pts = await ScoringEngine.get_team_matchday_points(t["id"], matchday_id)
            results.append({
                "team_id": t["id"],
                "team_name": t["team_name"],
                "display_name": t.get("display_name") or t["owner_nick"],
                "points": pts,
            })
        results.sort(key=lambda x: x["points"], reverse=True)
        return results
    finally:
        await db.close()


@router.post("/scoring/sync")
async def sync_from_simulator():
    """Pull finished matches from simulator and calculate fantasy points.
    Called by CronJob every 60 seconds or manually."""
    from src.backend.services.sync_service import sync_results
    return await sync_results()


@router.get("/scoring/sync-status")
async def get_sync_status():
    """Get the current sync state."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT * FROM sync_state")
        state = {r["key"]: r["value"] for r in rows}
        
        synced = await db.execute_fetchall(
            "SELECT COUNT(DISTINCT match_id) as matches, COUNT(*) as scores FROM match_scores WHERE match_id IS NOT NULL"
        )
        return {
            "last_sync": state.get("last_sync"),
            "synced_matches": synced[0]["matches"] if synced else 0,
            "synced_scores": synced[0]["scores"] if synced else 0,
        }
    finally:
        await db.close()


@router.get("/scoring/leaderboard")
async def get_leaderboard(auth: dict = Depends(get_current_team)):
    """Get fantasy league leaderboard — total points per team across all matchdays."""
    from src.backend.services.scoring_engine import ScoringEngine
    league_id = auth["league_id"]
    db = await get_db()
    try:
        teams = await db.execute_fetchall(
            "SELECT id, team_name, owner_nick, display_name FROM fantasy_teams WHERE league_id=$1",
            (league_id,),
        )
        
        # Get all completed matchdays
        matchdays = await db.execute_fetchall(
            "SELECT DISTINCT matchday_id FROM match_scores WHERE match_id IS NOT NULL"
        )
        md_ids = [m["matchday_id"] for m in matchdays]
        
        results = []
        for t in teams:
            t = dict(t)
            total_pts = 0
            md_points = {}
            for md_id in md_ids:
                pts = await ScoringEngine.get_team_matchday_points(t["id"], md_id)
                total_pts += pts
                md_points[md_id] = pts
            
            results.append({
                "team_id": t["id"],
                "team_name": t["team_name"],
                "display_name": t.get("display_name") or t["owner_nick"],
                "total_points": total_pts,
                "matchday_points": md_points,
                "matchdays_played": len([p for p in md_points.values() if p > 0]),
            })
        
        results.sort(key=lambda x: x["total_points"], reverse=True)
        return results
    finally:
        await db.close()


# ─── Matchday Lineup Management ───

@router.get("/lineup/{matchday_id}")
async def get_matchday_lineup(matchday_id: str, auth: dict = Depends(get_current_team)):
    """Get current matchday lineup with played/available status for each player."""
    from src.backend.services.lineup_service import get_lineup_status
    return await get_lineup_status(auth["team_id"], matchday_id)


@router.post("/lineup/{matchday_id}/swap")
async def swap_lineup_player(matchday_id: str, body: dict, auth: dict = Depends(get_current_team)):
    """Swap a starter with a bench player during a live matchday.
    
    Body: {"starter_out": "player_id", "bench_in": "player_id"}
    
    Rules:
    - Matchday must have started (at least 1 match finished)
    - bench_in player's country must NOT have played yet
    - starter_out can be any starter (played or not)
    - Removing a starter who scored = lose their points
    """
    from src.backend.services.lineup_service import swap_player
    
    starter_out = body.get("starter_out")
    bench_in = body.get("bench_in")
    
    if not starter_out or not bench_in:
        raise HTTPException(400, "Provide starter_out and bench_in player IDs")
    
    result = await swap_player(auth["team_id"], matchday_id, bench_in, starter_out)
    
    if "error" in result:
        raise HTTPException(400, result["error"])
    
    return result
