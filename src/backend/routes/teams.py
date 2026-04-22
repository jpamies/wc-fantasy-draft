from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
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
                      p.club, p.photo, p.market_value, p.clause_value,
                      COALESCE(pts.total, 0) as total_points
               FROM team_players tp JOIN players p ON tp.player_id=p.id
               LEFT JOIN (
                   SELECT player_id, SUM(total_points) as total
                   FROM match_scores GROUP BY player_id
               ) pts ON pts.player_id = tp.player_id
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
                total_points=p["total_points"],
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
            if len(body.starters) > 11:
                raise HTTPException(400, "Maximum 11 starters")

            # Verify all players belong to team
            if body.starters:
                placeholders = ",".join("?" for _ in body.starters)
                starter_rows = await db.execute_fetchall(
                    f"""SELECT tp.player_id, p.position FROM team_players tp
                        JOIN players p ON tp.player_id=p.id
                        WHERE tp.team_id=? AND tp.player_id IN ({placeholders})""",
                    [team_id] + body.starters,
                )
                if len(starter_rows) != len(body.starters):
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


# --- Matchday-specific lineups ---

@router.get("/teams/{team_id}/matchday-lineup/{matchday_id}")
async def get_matchday_lineup(team_id: str, matchday_id: str, auth: dict = Depends(get_current_team)):
    """Get lineup for a specific matchday. Creates from defaults if not exists."""
    db = await get_db()
    try:
        # Check if matchday lineup exists
        existing = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM matchday_lineups WHERE team_id=? AND matchday_id=?",
            (team_id, matchday_id),
        )
        if existing[0]["cnt"] == 0:
            # Copy from default team_players
            defaults = await db.execute_fetchall(
                "SELECT player_id, is_starter, is_captain, is_vice_captain FROM team_players WHERE team_id=?",
                (team_id,),
            )
            for d in defaults:
                d = dict(d)
                await db.execute(
                    "INSERT INTO matchday_lineups (team_id, matchday_id, player_id, is_starter, is_captain, is_vice_captain) VALUES (?,?,?,?,?,?)",
                    (team_id, matchday_id, d["player_id"], d["is_starter"], d["is_captain"], d["is_vice_captain"]),
                )
            await db.commit()

        # Fetch lineup with player details
        rows = await db.execute_fetchall(
            """SELECT ml.player_id, ml.is_starter, ml.is_captain, ml.is_vice_captain,
                      p.name, p.country_code, p.position, p.club, p.photo, p.market_value,
                      COALESCE(pts.total, 0) as total_points
               FROM matchday_lineups ml
               JOIN players p ON ml.player_id = p.id
               LEFT JOIN (SELECT player_id, SUM(total_points) as total FROM match_scores GROUP BY player_id) pts
                   ON pts.player_id = ml.player_id
               WHERE ml.team_id=? AND ml.matchday_id=?
               ORDER BY ml.is_starter DESC""",
            (team_id, matchday_id),
        )

        # Get match kickoff times to determine lock status
        matches = await db.execute_fetchall(
            "SELECT home_country, away_country, kickoff, status FROM matches WHERE matchday_id=?",
            (matchday_id,),
        )
        now = datetime.now(timezone.utc).isoformat()
        locked_countries = set()
        for m in matches:
            m = dict(m)
            if m["status"] in ("live", "finished") or (m["kickoff"] and m["kickoff"] <= now):
                locked_countries.add(m["home_country"])
                locked_countries.add(m["away_country"])

        players = []
        for r in rows:
            r = dict(r)
            r["locked"] = r["country_code"] in locked_countries
            players.append(r)

        return {"matchday_id": matchday_id, "team_id": team_id, "players": players}
    finally:
        await db.close()


@router.patch("/teams/{team_id}/matchday-lineup/{matchday_id}")
async def update_matchday_lineup(team_id: str, matchday_id: str, body: LineupUpdate, auth: dict = Depends(get_current_team)):
    """Update matchday-specific lineup with lock validation."""
    if auth["team_id"] != team_id:
        raise HTTPException(403, "Not your team")

    db = await get_db()
    try:
        # Get locked countries (matches started or finished)
        matches = await db.execute_fetchall(
            "SELECT home_country, away_country, kickoff, status FROM matches WHERE matchday_id=?",
            (matchday_id,),
        )
        now = datetime.now(timezone.utc).isoformat()
        locked_countries = set()
        for m in matches:
            m = dict(m)
            if m["status"] in ("live", "finished") or (m["kickoff"] and m["kickoff"] <= now):
                locked_countries.add(m["home_country"])
                locked_countries.add(m["away_country"])

        # Ensure matchday lineup exists
        existing = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM matchday_lineups WHERE team_id=? AND matchday_id=?",
            (team_id, matchday_id),
        )
        if existing[0]["cnt"] == 0:
            # Copy defaults first
            defaults = await db.execute_fetchall(
                "SELECT player_id, is_starter, is_captain, is_vice_captain FROM team_players WHERE team_id=?",
                (team_id,),
            )
            for d in defaults:
                d = dict(d)
                await db.execute(
                    "INSERT INTO matchday_lineups (team_id, matchday_id, player_id, is_starter, is_captain, is_vice_captain) VALUES (?,?,?,?,?,?)",
                    (team_id, matchday_id, d["player_id"], d["is_starter"], d["is_captain"], d["is_vice_captain"]),
                )

        if body.starters is not None:
            if len(body.starters) > 11:
                raise HTTPException(400, "Maximum 11 starters")

            # Validate: can't ADD a locked player as starter (their match started)
            current_starters = await db.execute_fetchall(
                "SELECT ml.player_id FROM matchday_lineups ml WHERE ml.team_id=? AND ml.matchday_id=? AND ml.is_starter=1",
                (team_id, matchday_id),
            )
            current_starter_ids = {dict(r)["player_id"] for r in current_starters}
            new_starters = set(body.starters)

            # Players being promoted from bench to starter
            promoted = new_starters - current_starter_ids
            for pid in promoted:
                player = await db.execute_fetchall("SELECT country_code FROM players WHERE id=?", (pid,))
                if player and dict(player[0])["country_code"] in locked_countries:
                    pname = await db.execute_fetchall("SELECT name FROM players WHERE id=?", (pid,))
                    name = dict(pname[0])["name"] if pname else pid
                    raise HTTPException(409, f"No puedes titular a {name}: su partido ya ha empezado")

            # Update lineup
            await db.execute(
                "UPDATE matchday_lineups SET is_starter=0 WHERE team_id=? AND matchday_id=?",
                (team_id, matchday_id),
            )
            for pid in body.starters:
                await db.execute(
                    "UPDATE matchday_lineups SET is_starter=1 WHERE team_id=? AND matchday_id=? AND player_id=?",
                    (team_id, matchday_id, pid),
                )

        if body.captain:
            # Can't set captain if locked
            cp = await db.execute_fetchall("SELECT country_code FROM players WHERE id=?", (body.captain,))
            if cp and dict(cp[0])["country_code"] in locked_countries:
                raise HTTPException(409, "No puedes cambiar el capitán: su partido ya ha empezado")
            await db.execute("UPDATE matchday_lineups SET is_captain=0 WHERE team_id=? AND matchday_id=?", (team_id, matchday_id))
            await db.execute("UPDATE matchday_lineups SET is_captain=1 WHERE team_id=? AND matchday_id=? AND player_id=?", (team_id, matchday_id, body.captain))

        if body.vice_captain:
            vcp = await db.execute_fetchall("SELECT country_code FROM players WHERE id=?", (body.vice_captain,))
            if vcp and dict(vcp[0])["country_code"] in locked_countries:
                raise HTTPException(409, "No puedes cambiar el vice-capitán: su partido ya ha empezado")
            await db.execute("UPDATE matchday_lineups SET is_vice_captain=0 WHERE team_id=? AND matchday_id=?", (team_id, matchday_id))
            await db.execute("UPDATE matchday_lineups SET is_vice_captain=1 WHERE team_id=? AND matchday_id=? AND player_id=?", (team_id, matchday_id, body.vice_captain))

        await db.commit()
        return {"ok": True}
    finally:
        await db.close()
