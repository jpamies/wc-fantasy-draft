import uuid
import string
import random
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from src.backend.database import get_db
from src.backend.auth import create_token, get_current_team
from src.backend.models import (
    AuthJoin, AuthRecover, AuthResponse,
    LeagueCreate, LeagueOut, LeagueSettings, StandingEntry,
)

router = APIRouter(prefix="/api/v1", tags=["leagues"])


def _gen_code(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


@router.post("/leagues", response_model=LeagueOut)
async def create_league(body: LeagueCreate):
    db = await get_db()
    try:
        league_id = f"league-{uuid.uuid4().hex[:8]}"
        code = _gen_code()
        now = datetime.now(timezone.utc).isoformat()
        s = body.settings or LeagueSettings()

        await db.execute(
            """INSERT INTO leagues (id, name, code, mode, status, max_teams, initial_budget,
               draft_timer_seconds, max_clausulazos_per_window, auto_substitutions,
               draft_order, captain_multiplier, created_at)
               VALUES (?,?,?,'draft','setup',?,?,?,?,?,?,?,?)""",
            (league_id, body.name, code,
             s.max_teams or 8, s.initial_budget or 500000000,
             s.draft_timer_seconds or 60, s.max_clausulazos_per_window or 2,
             1 if s.auto_substitutions is None else int(s.auto_substitutions),
             s.draft_order or "snake", s.captain_multiplier or 2.0, now),
        )
        await db.commit()
        return LeagueOut(id=league_id, name=body.name, code=code,
                         max_teams=s.max_teams or 8, initial_budget=s.initial_budget or 500000000,
                         draft_timer_seconds=s.draft_timer_seconds or 60,
                         max_clausulazos_per_window=s.max_clausulazos_per_window or 2,
                         draft_order=s.draft_order or "snake",
                         captain_multiplier=s.captain_multiplier or 2.0)
    finally:
        await db.close()


@router.post("/auth/join", response_model=AuthResponse)
async def join_league(body: AuthJoin):
    db = await get_db()
    try:
        row = await db.execute_fetchall("SELECT * FROM leagues WHERE code=?", (body.league_code,))
        if not row:
            raise HTTPException(404, "League not found")
        league = dict(row[0])

        # Check if nickname already taken in this league
        existing = await db.execute_fetchall(
            "SELECT id FROM fantasy_teams WHERE league_id=? AND owner_nick=?",
            (league["id"], body.nickname),
        )
        if existing:
            raise HTTPException(409, "Nickname already taken in this league")

        # Cannot join after draft has started
        if league["status"] not in ("setup", "draft_pending"):
            raise HTTPException(409, "League already started — cannot join after draft begins")

        # Check team count
        teams = await db.execute_fetchall("SELECT COUNT(*) as cnt FROM fantasy_teams WHERE league_id=?", (league["id"],))
        if teams[0]["cnt"] >= league["max_teams"]:
            raise HTTPException(409, "League is full")

        team_id = f"team-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO fantasy_teams (id, league_id, owner_nick, team_name, budget, formation, created_at) VALUES (?,?,?,?,?,?,?)",
            (team_id, league["id"], body.nickname, body.team_name, league["initial_budget"], "4-3-3", now),
        )

        # First team becomes commissioner
        is_commissioner = not league["commissioner_team_id"]
        if is_commissioner:
            await db.execute("UPDATE leagues SET commissioner_team_id=? WHERE id=?", (team_id, league["id"]))

        await db.commit()
        token = create_token(team_id, league["id"], is_commissioner)
        return AuthResponse(token=token, team_id=team_id, league_id=league["id"], is_commissioner=is_commissioner)
    finally:
        await db.close()


@router.post("/auth/recover", response_model=AuthResponse)
async def recover_session(body: AuthRecover):
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT ft.id as team_id, ft.league_id, l.commissioner_team_id
               FROM fantasy_teams ft JOIN leagues l ON ft.league_id=l.id
               WHERE l.code=? AND ft.owner_nick=?""",
            (body.league_code, body.nickname),
        )
        if not rows:
            raise HTTPException(404, "Team not found")
        r = dict(rows[0])
        is_comm = r["commissioner_team_id"] == r["team_id"]
        token = create_token(r["team_id"], r["league_id"], is_comm)
        return AuthResponse(token=token, team_id=r["team_id"], league_id=r["league_id"], is_commissioner=is_comm)
    finally:
        await db.close()


@router.get("/leagues/{league_id}", response_model=LeagueOut)
async def get_league(league_id: str):
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT * FROM leagues WHERE id=?", (league_id,))
        if not rows:
            raise HTTPException(404, "League not found")
        lg = dict(rows[0])
        teams = await db.execute_fetchall("SELECT id, owner_nick, team_name, budget FROM fantasy_teams WHERE league_id=?", (league_id,))
        return LeagueOut(
            id=lg["id"], name=lg["name"], code=lg["code"],
            commissioner_team_id=lg["commissioner_team_id"],
            mode=lg["mode"], status=lg["status"],
            max_teams=lg["max_teams"], initial_budget=lg["initial_budget"],
            draft_timer_seconds=lg["draft_timer_seconds"],
            max_clausulazos_per_window=lg["max_clausulazos_per_window"],
            auto_substitutions=bool(lg["auto_substitutions"]),
            draft_order=lg["draft_order"],
            captain_multiplier=lg["captain_multiplier"],
            transfer_window_open=bool(lg["transfer_window_open"]),
            teams=[dict(t) for t in teams],
        )
    finally:
        await db.close()


@router.get("/leagues/{league_id}/standings", response_model=list[StandingEntry])
async def get_standings(league_id: str):
    db = await get_db()
    try:
        teams = await db.execute_fetchall(
            "SELECT id, owner_nick, team_name, budget FROM fantasy_teams WHERE league_id=?", (league_id,)
        )
        standings = []
        for t in teams:
            t = dict(t)
            # Sum points from all matchdays for this team's starters
            pts_rows = await db.execute_fetchall(
                """SELECT COALESCE(SUM(ms.total_points), 0) as pts
                   FROM match_scores ms
                   JOIN team_players tp ON ms.player_id = tp.player_id AND tp.team_id=?
                   WHERE tp.is_starter=1""",
                (t["id"],),
            )
            total = pts_rows[0]["pts"] if pts_rows else 0
            # Apply captain multiplier
            cap_rows = await db.execute_fetchall(
                """SELECT COALESCE(SUM(ms.total_points), 0) as pts
                   FROM match_scores ms
                   JOIN team_players tp ON ms.player_id = tp.player_id AND tp.team_id=?
                   WHERE tp.is_captain=1""",
                (t["id"],),
            )
            cap_pts = cap_rows[0]["pts"] if cap_rows else 0
            # Captain already counted once in total, add extra multiplier portion
            total += cap_pts  # effectively x2

            standings.append(StandingEntry(
                team_id=t["id"], team_name=t["team_name"],
                owner_nick=t["owner_nick"], total_points=total, budget=t["budget"]
            ))
        standings.sort(key=lambda x: x.total_points, reverse=True)
        return standings
    finally:
        await db.close()


@router.patch("/leagues/{league_id}/settings")
async def update_settings(league_id: str, body: LeagueSettings, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id or not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    db = await get_db()
    try:
        updates = []
        params = []
        for field, col in [
            ("max_teams", "max_teams"), ("initial_budget", "initial_budget"),
            ("draft_timer_seconds", "draft_timer_seconds"),
            ("max_clausulazos_per_window", "max_clausulazos_per_window"),
            ("draft_order", "draft_order"), ("captain_multiplier", "captain_multiplier"),
        ]:
            val = getattr(body, field, None)
            if val is not None:
                updates.append(f"{col}=?")
                params.append(val)
        if body.auto_substitutions is not None:
            updates.append("auto_substitutions=?")
            params.append(int(body.auto_substitutions))
        if updates:
            params.append(league_id)
            await db.execute(f"UPDATE leagues SET {', '.join(updates)} WHERE id=?", params)
            await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# --- My leagues (list all leagues for a Clerk user) ---

@router.get("/my-leagues")
async def my_leagues(nickname: str):
    """Return all leagues where this user (Clerk ID) has a team."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT l.id, l.name, l.code, l.status, ft.id as team_id, ft.team_name,
                      l.commissioner_team_id
               FROM fantasy_teams ft JOIN leagues l ON ft.league_id = l.id
               WHERE ft.owner_nick = ?
               ORDER BY ft.created_at DESC""",
            (nickname,),
        )
        return [
            {
                "league_id": dict(r)["id"],
                "league_name": dict(r)["name"],
                "league_code": dict(r)["code"],
                "status": dict(r)["status"],
                "team_id": dict(r)["team_id"],
                "team_name": dict(r)["team_name"],
                "is_commissioner": dict(r)["commissioner_team_id"] == dict(r)["team_id"],
            }
            for r in rows
        ]
    finally:
        await db.close()


# --- Leave league ---

@router.delete("/leagues/{league_id}/leave")
async def leave_league(league_id: str, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    if auth.get("is_commissioner"):
        raise HTTPException(409, "Commissioner cannot leave — delete the league instead")
    db = await get_db()
    try:
        # Delete team's players first
        await db.execute("DELETE FROM team_players WHERE team_id=?", (auth["team_id"],))
        # Delete the team
        await db.execute("DELETE FROM fantasy_teams WHERE id=?", (auth["team_id"],))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# --- Delete league (commissioner only) ---

@router.delete("/leagues/{league_id}")
async def delete_league(league_id: str, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id or not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    db = await get_db()
    try:
        # Delete all team players in this league
        await db.execute(
            "DELETE FROM team_players WHERE team_id IN (SELECT id FROM fantasy_teams WHERE league_id=?)",
            (league_id,),
        )
        # Delete all teams
        await db.execute("DELETE FROM fantasy_teams WHERE league_id=?", (league_id,))
        # Delete the league
        await db.execute("DELETE FROM leagues WHERE id=?", (league_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()
