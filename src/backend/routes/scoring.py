import uuid
import json
import os
from fastapi import APIRouter, HTTPException, Depends
from src.backend.auth import get_current_team
from src.backend.database import get_db
from src.backend.services.scoring_engine import ScoringEngine
from src.backend.models import MatchdayCreate, MatchCreate, MatchResultUpdate, ScoreBatchEntry

router = APIRouter(prefix="/api/v1", tags=["scoring"])


@router.get("/scoring/matchdays")
async def list_matchdays():
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT * FROM matchdays ORDER BY date")
        return [dict(r) for r in rows]
    finally:
        await db.close()


@router.post("/scoring/matchdays")
async def create_matchday(body: MatchdayCreate, auth: dict = Depends(get_current_team)):
    if not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO matchdays (id, name, date, phase, status) VALUES (?,?,?,?,?)",
            (body.id, body.name, body.date, body.phase, "upcoming"),
        )
        await db.commit()
        return {"ok": True, "id": body.id}
    finally:
        await db.close()


@router.get("/scoring/matchdays/{matchday_id}")
async def get_matchday(matchday_id: str):
    db = await get_db()
    try:
        md = await db.execute_fetchall("SELECT * FROM matchdays WHERE id=?", (matchday_id,))
        if not md:
            raise HTTPException(404, "Matchday not found")
        matches = await db.execute_fetchall(
            """SELECT m.*, ch.name as home_name, ch.flag as home_flag,
                      ca.name as away_name, ca.flag as away_flag
               FROM matches m
               JOIN countries ch ON m.home_country=ch.code
               JOIN countries ca ON m.away_country=ca.code
               WHERE m.matchday_id=?""",
            (matchday_id,),
        )
        scores = await db.execute_fetchall(
            """SELECT ms.*, p.name as player_name, p.position, p.country_code
               FROM match_scores ms JOIN players p ON ms.player_id=p.id
               WHERE ms.matchday_id=? ORDER BY ms.total_points DESC""",
            (matchday_id,),
        )
        return {
            **dict(md[0]),
            "matches": [dict(m) for m in matches],
            "scores": [dict(s) for s in scores],
        }
    finally:
        await db.close()


@router.post("/scoring/matchdays/{matchday_id}/matches")
async def add_match(matchday_id: str, body: MatchCreate, auth: dict = Depends(get_current_team)):
    if not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO matches (id, matchday_id, home_country, away_country, kickoff, status) VALUES (?,?,?,?,?,?)",
            (body.id, matchday_id, body.home_country, body.away_country, body.kickoff, "scheduled"),
        )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@router.patch("/scoring/matches/{match_id}/result")
async def update_result(match_id: str, body: MatchResultUpdate, auth: dict = Depends(get_current_team)):
    if not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    db = await get_db()
    try:
        await db.execute(
            "UPDATE matches SET score_home=?, score_away=?, status='finished' WHERE id=?",
            (body.score_home, body.score_away, match_id),
        )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@router.post("/scoring/matchdays/{matchday_id}/scores")
async def submit_scores(matchday_id: str, body: ScoreBatchEntry, auth: dict = Depends(get_current_team)):
    if not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    scores = [s.model_dump() for s in body.scores]
    results = await ScoringEngine.process_match_scores(matchday_id, body.match_id, scores)
    # Mark matchday as completed if all matches finished
    db = await get_db()
    try:
        unfinished = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM matches WHERE matchday_id=? AND status!='finished'",
            (matchday_id,),
        )
        if unfinished[0]["cnt"] == 0:
            await db.execute("UPDATE matchdays SET status='completed' WHERE id=?", (matchday_id,))
            await db.commit()
    finally:
        await db.close()
    return {"ok": True, "scores": results}


@router.get("/scoring/matchdays/{matchday_id}/fantasy-points")
async def get_fantasy_points(matchday_id: str, auth: dict = Depends(get_current_team)):
    """Get all fantasy teams' points for a specific matchday."""
    from src.backend.services.scoring_engine import ScoringEngine
    league_id = auth["league_id"]
    db = await get_db()
    try:
        teams = await db.execute_fetchall(
            "SELECT id, team_name, owner_nick, display_name FROM fantasy_teams WHERE league_id=?",
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


@router.post("/scoring/populate-calendar")
async def populate_calendar(auth: dict = Depends(get_current_team)):
    """Pre-populate matchdays and matches from data/tournament/calendar.json. Commissioner only."""
    if not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    
    calendar_path = os.path.join("data", "tournament", "calendar.json")
    if not os.path.exists(calendar_path):
        raise HTTPException(404, "Calendar file not found")
    
    with open(calendar_path, "r", encoding="utf-8") as f:
        calendar = json.load(f)
    
    db = await get_db()
    try:
        created_matchdays = 0
        created_matches = 0
        for md in calendar:
            # Skip if matchday already exists
            existing = await db.execute_fetchall("SELECT id FROM matchdays WHERE id=?", (md["id"],))
            if existing:
                continue
            await db.execute(
                "INSERT INTO matchdays (id, name, date, phase, status) VALUES (?,?,?,?,?)",
                (md["id"], md["name"], md.get("date", ""), md.get("phase", "groups"), "upcoming"),
            )
            created_matchdays += 1
            for m in md.get("matches", []):
                await db.execute(
                    "INSERT INTO matches (id, matchday_id, home_country, away_country, kickoff, status) VALUES (?,?,?,?,?,?)",
                    (m["id"], md["id"], m["home"], m["away"], m.get("kickoff", ""), "scheduled"),
                )
                created_matches += 1
        await db.commit()
        return {"ok": True, "matchdays_created": created_matchdays, "matches_created": created_matches}
    finally:
        await db.close()


@router.post("/scoring/matchdays/{matchday_id}/simulate")
async def simulate_matchday(matchday_id: str, auth: dict = Depends(get_current_team)):
    """Simulate realistic scores for testing. Commissioner only."""
    if not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    from src.scripts.fetch_scores import simulate_match_scores
    await simulate_match_scores(matchday_id)
    return {"ok": True}


@router.post("/scoring/matchdays/{matchday_id}/reset")
async def reset_matchday_scores(matchday_id: str, auth: dict = Depends(get_current_team)):
    """Reset all scores and results for a matchday. Commissioner only."""
    if not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    db = await get_db()
    try:
        # Delete all match scores for this matchday
        await db.execute("DELETE FROM match_scores WHERE matchday_id=?", (matchday_id,))
        # Reset match results
        await db.execute(
            "UPDATE matches SET score_home=NULL, score_away=NULL, status='scheduled' WHERE matchday_id=?",
            (matchday_id,),
        )
        # Reset matchday status
        await db.execute("UPDATE matchdays SET status='upcoming' WHERE id=?", (matchday_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@router.delete("/scoring/reset-all")
async def reset_all_scores(auth: dict = Depends(get_current_team)):
    """Reset ALL matchdays, matches, and scores. Commissioner only."""
    if not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    db = await get_db()
    try:
        await db.execute("DELETE FROM match_scores")
        await db.execute("DELETE FROM matchday_lineups")
        await db.execute("DELETE FROM matches")
        await db.execute("DELETE FROM matchdays")
        await db.execute("DELETE FROM sync_state")
        await db.commit()
        return {"ok": True}
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
            "SELECT id, team_name, owner_nick, display_name FROM fantasy_teams WHERE league_id=?",
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
