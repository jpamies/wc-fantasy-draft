from fastapi import APIRouter, HTTPException, Depends
from src.backend.database import get_db
from src.backend.auth import get_current_team
from src.backend.models import TeamOut, TeamPlayerOut, LineupUpdate

router = APIRouter(prefix="/api/v1", tags=["teams"])

FORMATIONS = {
    "4-3-3": {"DEF": 4, "MID": 3, "FWD": 3},
    "4-4-2": {"DEF": 4, "MID": 4, "FWD": 2},
    "3-5-2": {"DEF": 3, "MID": 5, "FWD": 2},
    "3-4-3": {"DEF": 3, "MID": 4, "FWD": 3},
    "5-3-2": {"DEF": 5, "MID": 3, "FWD": 2},
    "5-4-1": {"DEF": 5, "MID": 4, "FWD": 1},
    "4-5-1": {"DEF": 4, "MID": 5, "FWD": 1},
}


@router.get("/teams/{team_id}", response_model=TeamOut)
async def get_team(team_id: str):
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT * FROM fantasy_teams WHERE id=?", (team_id,))
        if not rows:
            raise HTTPException(404, "Team not found")
        team = dict(rows[0])

        players = await db.execute_fetchall(
            """SELECT tp.*, p.name, p.country_code, p.position, p.detailed_position,
                      p.club, p.photo, p.market_value, p.clause_value
               FROM team_players tp JOIN players p ON tp.player_id=p.id
               WHERE tp.team_id=? ORDER BY tp.is_starter DESC, tp.bench_order ASC""",
            (team_id,),
        )
        player_list = [
            TeamPlayerOut(
                player_id=p["player_id"], name=p["name"], country_code=p["country_code"],
                position=p["position"], detailed_position=p["detailed_position"],
                club=p["club"], photo=p["photo"], market_value=p["market_value"],
                clause_value=p["clause_value"], is_starter=bool(p["is_starter"]),
                position_slot=p["position_slot"] or "", is_captain=bool(p["is_captain"]),
                is_vice_captain=bool(p["is_vice_captain"]),
                bench_order=p["bench_order"], acquired_via=p["acquired_via"],
            ).model_dump()
            for p in players
        ]
        return TeamOut(
            id=team["id"], league_id=team["league_id"],
            owner_nick=team["owner_nick"], team_name=team["team_name"],
            budget=team["budget"], formation=team["formation"], players=player_list,
        )
    finally:
        await db.close()


@router.patch("/teams/{team_id}/lineup")
async def update_lineup(team_id: str, body: LineupUpdate, auth: dict = Depends(get_current_team)):
    if auth["team_id"] != team_id:
        raise HTTPException(403, "Not your team")

    db = await get_db()
    try:
        if body.formation and body.formation not in FORMATIONS:
            raise HTTPException(400, f"Invalid formation. Allowed: {list(FORMATIONS.keys())}")

        if body.formation:
            await db.execute("UPDATE fantasy_teams SET formation=? WHERE id=?", (body.formation, team_id))

        if body.starters is not None:
            formation = body.formation
            if not formation:
                t = await db.execute_fetchall("SELECT formation FROM fantasy_teams WHERE id=?", (team_id,))
                formation = t[0]["formation"] if t else "4-3-3"

            req = FORMATIONS[formation]
            # Validate starters count = 11
            if len(body.starters) != 11:
                raise HTTPException(400, "Must have exactly 11 starters")

            # Verify all players belong to team
            placeholders = ",".join("?" for _ in body.starters)
            starter_rows = await db.execute_fetchall(
                f"""SELECT tp.player_id, p.position FROM team_players tp
                    JOIN players p ON tp.player_id=p.id
                    WHERE tp.team_id=? AND tp.player_id IN ({placeholders})""",
                [team_id] + body.starters,
            )
            if len(starter_rows) != 11:
                raise HTTPException(400, "Some players not in your team")

            # Reset all, then set starters
            await db.execute("UPDATE team_players SET is_starter=0 WHERE team_id=?", (team_id,))
            for pid in body.starters:
                await db.execute("UPDATE team_players SET is_starter=1 WHERE team_id=? AND player_id=?", (team_id, pid))

            # Auto-assign bench order for non-starters
            bench = await db.execute_fetchall(
                "SELECT player_id FROM team_players WHERE team_id=? AND is_starter=0 ORDER BY player_id",
                (team_id,),
            )
            for i, b in enumerate(bench):
                await db.execute(
                    "UPDATE team_players SET bench_order=? WHERE team_id=? AND player_id=?",
                    (i + 1, team_id, b["player_id"]),
                )

        if body.captain:
            await db.execute("UPDATE team_players SET is_captain=0 WHERE team_id=?", (team_id,))
            await db.execute("UPDATE team_players SET is_captain=1 WHERE team_id=? AND player_id=?", (team_id, body.captain))

        if body.vice_captain:
            await db.execute("UPDATE team_players SET is_vice_captain=0 WHERE team_id=?", (team_id,))
            await db.execute("UPDATE team_players SET is_vice_captain=1 WHERE team_id=? AND player_id=?", (team_id, body.vice_captain))

        await db.commit()
        return {"ok": True}
    finally:
        await db.close()
