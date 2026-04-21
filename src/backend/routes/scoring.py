import uuid
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
