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
             s.max_teams or 10, s.initial_budget or 500000000,
             s.draft_timer_seconds or 60, s.max_clausulazos_per_window or 2,
             1 if s.auto_substitutions is None else int(s.auto_substitutions),
             s.draft_order or "snake", s.captain_multiplier or 2.0, now),
        )
        await db.commit()
        return LeagueOut(id=league_id, name=body.name, code=code,
                         max_teams=s.max_teams or 10, initial_budget=s.initial_budget or 500000000,
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
            "INSERT INTO fantasy_teams (id, league_id, owner_nick, display_name, team_name, budget, formation, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (team_id, league["id"], body.nickname, body.display_name, body.team_name, league["initial_budget"], "4-3-3", now),
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
        teams = await db.execute_fetchall("SELECT id, owner_nick, display_name, team_name, budget FROM fantasy_teams WHERE league_id=?", (league_id,))
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


@router.get("/leagues/{league_id}/standings")
async def get_standings(league_id: str):
    """Full standings with per-matchday breakdown."""
    from src.backend.services.scoring_engine import ScoringEngine
    db = await get_db()
    try:
        teams = await db.execute_fetchall(
            "SELECT id, owner_nick, display_name, team_name, budget FROM fantasy_teams WHERE league_id=?", (league_id,)
        )
        matchdays = await db.execute_fetchall(
            "SELECT id FROM matchdays WHERE status IN ('active', 'completed') ORDER BY id"
        )
        md_ids = [dict(md)["id"] for md in matchdays]

        standings = []
        for t in teams:
            t = dict(t)
            total = 0
            md_points = {}
            for md_id in md_ids:
                pts = await ScoringEngine.get_team_matchday_points(t["id"], md_id)
                total += pts
                md_points[md_id] = pts
            standings.append({
                "team_id": t["id"], "team_name": t["team_name"],
                "owner_nick": t["owner_nick"],
                "display_name": t.get("display_name") or t["owner_nick"],
                "total_points": total, "budget": t["budget"],
                "matchday_points": md_points,
            })
        standings.sort(key=lambda x: x["total_points"], reverse=True)
        return {"standings": standings, "matchday_ids": md_ids}
    finally:
        await db.close()


@router.get("/leagues/{league_id}/team-lineup/{team_id}/{matchday_id}")
async def get_team_lineup_public(league_id: str, team_id: str, matchday_id: str):
    """Read-only view of a team's lineup for a matchday (for standings detail)."""
    db = await get_db()
    try:
        # Verify team belongs to league
        team = await db.execute_fetchall(
            "SELECT id FROM fantasy_teams WHERE id=? AND league_id=?", (team_id, league_id)
        )
        if not team:
            raise HTTPException(404, "Team not found in this league")

        rows = await db.execute_fetchall(
            """SELECT ml.player_id, ml.is_starter, ml.is_captain, ml.is_vice_captain,
                      p.name, p.country_code, p.position, p.club, p.photo,
                      COALESCE(ms.total_points, 0) as matchday_points,
                      COALESCE(ms.goals, 0) as goals,
                      COALESCE(ms.assists, 0) as assists,
                      COALESCE(ms.yellow_cards, 0) as yellow_cards,
                      COALESCE(ms.red_card, 0) as red_card,
                      COALESCE(ms.minutes_played, 0) as minutes_played
               FROM matchday_lineups ml
               JOIN players p ON ml.player_id = p.id
               LEFT JOIN match_scores ms ON ms.player_id = ml.player_id AND ms.matchday_id = ?
               WHERE ml.team_id=? AND ml.matchday_id=?
               ORDER BY ml.is_starter DESC, p.position""",
            (matchday_id, team_id, matchday_id),
        )
        if not rows:
            # Fall back to team_players
            rows = await db.execute_fetchall(
                """SELECT tp.player_id, tp.is_starter, tp.is_captain, tp.is_vice_captain,
                          p.name, p.country_code, p.position, p.club, p.photo,
                          COALESCE(ms.total_points, 0) as matchday_points,
                          COALESCE(ms.goals, 0) as goals,
                          COALESCE(ms.assists, 0) as assists,
                          COALESCE(ms.yellow_cards, 0) as yellow_cards,
                          COALESCE(ms.red_card, 0) as red_card,
                          COALESCE(ms.minutes_played, 0) as minutes_played
                   FROM team_players tp
                   JOIN players p ON tp.player_id = p.id
                   LEFT JOIN match_scores ms ON ms.player_id = tp.player_id AND ms.matchday_id = ?
                   WHERE tp.team_id=?
                   ORDER BY tp.is_starter DESC, p.position""",
                (matchday_id, team_id),
            )
        return {"players": [dict(r) for r in rows]}
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
        team_id = auth["team_id"]
        # Delete draft picks for this team
        await db.execute(
            "DELETE FROM draft_picks WHERE team_id=?", (team_id,)
        )
        # Delete transfers involving this team
        await db.execute(
            "DELETE FROM transfers WHERE from_team_id=? OR to_team_id=?", (team_id, team_id)
        )
        # Delete matchday lineups for this team
        await db.execute("DELETE FROM matchday_lineups WHERE team_id=?", (team_id,))
        # Delete team's players
        await db.execute("DELETE FROM team_players WHERE team_id=?", (team_id,))
        # Delete the team
        await db.execute("DELETE FROM fantasy_teams WHERE id=?", (team_id,))
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
        # Get draft id for this league
        draft_rows = await db.execute_fetchall(
            "SELECT id FROM drafts WHERE league_id=?", (league_id,)
        )
        for d in draft_rows:
            await db.execute("DELETE FROM draft_settings WHERE draft_id=?", (dict(d)["id"],))
            await db.execute("DELETE FROM draft_picks WHERE draft_id=?", (dict(d)["id"],))
        await db.execute("DELETE FROM drafts WHERE league_id=?", (league_id,))
        # Delete transfers
        await db.execute("DELETE FROM transfers WHERE league_id=?", (league_id,))
        # Delete matchday lineups for teams in this league
        await db.execute(
            "DELETE FROM matchday_lineups WHERE team_id IN (SELECT id FROM fantasy_teams WHERE league_id=?)",
            (league_id,),
        )
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


# --- Bots ---

@router.post("/leagues/{league_id}/admin/add-bots")
async def admin_add_bots(league_id: str, body: dict, auth: dict = Depends(get_current_team)):
    """Add bot teams. Body: {"count": 3}"""
    if auth["league_id"] != league_id or not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")

    count = body.get("count", 0)
    if not isinstance(count, int) or count < 0 or count > 10:
        raise HTTPException(400, "count must be 0-10")

    db = await get_db()
    try:
        league = await db.execute_fetchall("SELECT status FROM leagues WHERE id=?", (league_id,))
        if not league:
            raise HTTPException(404, "League not found")
        if dict(league[0])["status"] not in ("setup", "draft_pending"):
            raise HTTPException(409, "Solo se pueden añadir bots antes del draft")
    finally:
        await db.close()

    from src.backend.services.bot_service import create_bots
    created = await create_bots(league_id, count)
    return {"ok": True, "bots_created": len(created), "bots": created}


@router.delete("/leagues/{league_id}/admin/bots")
async def admin_remove_bots(league_id: str, auth: dict = Depends(get_current_team)):
    """Remove all bots from the league."""
    if auth["league_id"] != league_id or not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")

    from src.backend.services.bot_service import remove_bots
    removed = await remove_bots(league_id)
    return {"ok": True, "bots_removed": removed}


@router.post("/leagues/{league_id}/admin/reset")
async def admin_reset_league(league_id: str, auth: dict = Depends(get_current_team)):
    """Reset league to setup state. Keeps human teams, removes bots, clears all game data."""
    if auth["league_id"] != league_id or not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")

    from src.backend.services.bot_service import remove_bots
    db = await get_db()
    try:
        league = await db.execute_fetchall("SELECT * FROM leagues WHERE id=?", (league_id,))
        if not league:
            raise HTTPException(404, "League not found")
        league = dict(league[0])

        # 1. Delete drafts and related data
        draft_rows = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=?", (league_id,))
        for d in draft_rows:
            await db.execute("DELETE FROM draft_settings WHERE draft_id=?", (dict(d)["id"],))
            await db.execute("DELETE FROM draft_picks WHERE draft_id=?", (dict(d)["id"],))
        await db.execute("DELETE FROM drafts WHERE league_id=?", (league_id,))

        # 2. Clear all team players and lineups for this league
        await db.execute(
            "DELETE FROM matchday_lineups WHERE team_id IN (SELECT id FROM fantasy_teams WHERE league_id=?)",
            (league_id,),
        )
        await db.execute(
            "DELETE FROM team_players WHERE team_id IN (SELECT id FROM fantasy_teams WHERE league_id=?)",
            (league_id,),
        )

        # 3. Clear transfers
        await db.execute("DELETE FROM transfers WHERE league_id=?", (league_id,))

        # 4. Reset budgets for remaining human teams
        await db.execute(
            "UPDATE fantasy_teams SET budget=? WHERE league_id=? AND owner_nick NOT LIKE 'bot_%'",
            (league["initial_budget"], league_id),
        )

        # 5. Remove all bots
        bot_ids = await db.execute_fetchall(
            "SELECT id FROM fantasy_teams WHERE league_id=? AND owner_nick LIKE 'bot_%'",
            (league_id,),
        )
        if bot_ids:
            placeholders = ",".join("?" * len(bot_ids))
            ids = [b["id"] for b in bot_ids]
            await db.execute(f"DELETE FROM fantasy_teams WHERE id IN ({placeholders})", ids)

        # 6. Reset league status
        await db.execute(
            "UPDATE leagues SET status='setup', transfer_window_open=0 WHERE id=?",
            (league_id,),
        )

        await db.commit()
        return {"ok": True, "message": "Liga reseteada a estado inicial"}
    finally:
        await db.close()
