from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import logging
import traceback
from src.backend.database import get_db
from src.backend.auth import get_current_team
from src.backend.models import TeamOut, TeamPlayerOut, LineupUpdate, LineupSpec5, InGameSubstitutionRequest

router = APIRouter(prefix="/api/v1", tags=["teams"])
logger = logging.getLogger("wc-fantasy.teams")


async def _ensure_matchday_exists(db, matchday_id: str):
    """Ensure a matchday row exists in the local DB (for FK integrity).
    The calendar lives in the simulator — this just creates a stub if missing."""
    existing = await db.execute_fetchall("SELECT id FROM matchdays WHERE id=$1", (matchday_id,))
    if not existing:
        await db.execute(
            "INSERT INTO matchdays (id, name, date, phase, status) VALUES ($1,$2,$3,$4,$5) ON CONFLICT (id) DO NOTHING",
            (matchday_id, matchday_id, "", "groups", "upcoming"),
        )
        await db.commit()

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
    # Backfill any missing players from simulator (best-effort; never fail the GET).
    from src.backend.config import settings
    if settings.SIMULATOR_API_URL:
        try:
            from src.backend.services.simulator_client import ensure_team_players_in_db
            await ensure_team_players_in_db(team_id)
        except Exception as e:
            logger.warning("ensure_team_players_in_db failed for %s: %s", team_id, e)

    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT * FROM fantasy_teams WHERE id=$1", (team_id,))
        if not rows:
            raise HTTPException(404, "Team not found")
        team = dict(rows[0])

        players = await db.execute_fetchall(
            """SELECT tp.*, p.name, p.country_code, p.position, p.detailed_position,
                      p.club, p.photo, p.market_value, p.clause_value,
                      c.flag AS country_flag,
                      COALESCE(pts.total, 0) as total_points
               FROM team_players tp JOIN players p ON tp.player_id=p.id
               LEFT JOIN countries c ON c.code = p.country_code
               LEFT JOIN (
                   SELECT player_id, SUM(total_points) as total
                   FROM match_scores GROUP BY player_id
               ) pts ON pts.player_id = tp.player_id
               WHERE tp.team_id=$1 ORDER BY tp.is_starter DESC, tp.bench_order ASC""",
            (team_id,),
        )
        # Compute alive set once for is_alive flag (best-effort).
        try:
            from src.backend.services.market_service import get_alive_country_codes
            alive_codes = await get_alive_country_codes()
        except Exception as e:
            logger.warning("get_alive_country_codes failed: %s", e)
            alive_codes = None

        player_list = []
        for p in players:
            try:
                player_list.append(TeamPlayerOut(
                    player_id=p["player_id"], name=p["name"] or "",
                    country_code=p["country_code"] or "",
                    country_flag=p["country_flag"] or "",
                    position=p["position"] or "MID",
                    detailed_position=p["detailed_position"] or "",
                    club=p["club"] or "", photo=p["photo"] or "",
                    market_value=int(p["market_value"] or 0),
                    clause_value=int(p["clause_value"] or 0),
                    is_starter=bool(p["is_starter"]),
                    position_slot=p["position_slot"] or "",
                    is_captain=bool(p["is_captain"]),
                    is_vice_captain=bool(p["is_vice_captain"]),
                    bench_order=int(p["bench_order"] or 0),
                    acquired_via=p["acquired_via"] or "draft",
                    total_points=int(p["total_points"] or 0),
                    is_alive=(alive_codes is None) or (p["country_code"] in alive_codes),
                ).model_dump())
            except Exception as e:
                logger.error(
                    "Failed to build TeamPlayerOut for team=%s player=%s: %s\nrow=%r\n%s",
                    team_id, p.get("player_id"), e, dict(p), traceback.format_exc(),
                )
                # Skip this row rather than failing the whole team page.
                continue

        # Budget: prefer latest market_budgets remaining if available
        effective_budget = team["budget"]
        try:
            latest_mb = await db.execute_fetchall(
                """SELECT mb.remaining_budget
                   FROM market_budgets mb
                   JOIN market_windows mw ON mb.market_window_id = mw.id
                   WHERE mb.team_id = $1 AND mw.league_id = $2
                   ORDER BY mw.id DESC LIMIT 1""",
                (team_id, team["league_id"]),
            )
            if latest_mb:
                effective_budget = latest_mb[0]["remaining_budget"]
        except Exception:
            pass

        # Team fantasy points: sum from ScoringEngine across all matchdays
        team_total_points = 0
        try:
            from src.backend.services.scoring_engine import ScoringEngine
            md_rows = await db.execute_fetchall(
                "SELECT id FROM matchdays WHERE status IN ('active','completed')"
            )
            for md in md_rows:
                team_total_points += await ScoringEngine.get_team_matchday_points(team_id, md["id"])
        except Exception as e:
            logger.warning("Team points calculation failed: %s", e)

        return TeamOut(
            id=team["id"], league_id=team["league_id"],
            owner_nick=team["owner_nick"], team_name=team["team_name"],
            budget=effective_budget, formation=team["formation"],
            players=player_list, total_points=team_total_points,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_team failed for %s: %s\n%s", team_id, e, traceback.format_exc())
        raise HTTPException(500, f"{type(e).__name__}: {e}")
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
            await db.execute("UPDATE fantasy_teams SET formation=$1 WHERE id=$2", (body.formation, team_id))

        if body.starters is not None:
            if len(body.starters) > 11:
                raise HTTPException(400, "Maximum 11 starters")

            # Verify all players belong to team
            if body.starters:
                placeholders = ",".join(f"${i+2}" for i in range(len(body.starters)))
                starter_rows = await db.execute_fetchall(
                    f"""SELECT tp.player_id, p.position FROM team_players tp
                        JOIN players p ON tp.player_id=p.id
                        WHERE tp.team_id=$1 AND tp.player_id IN ({placeholders})""",
                    [team_id] + body.starters,
                )
                if len(starter_rows) != len(body.starters):
                    raise HTTPException(400, "Some players not in your team")

            # Reset all, then set starters
            await db.execute("UPDATE team_players SET is_starter=0 WHERE team_id=$1", (team_id,))
            for pid in body.starters:
                await db.execute("UPDATE team_players SET is_starter=1 WHERE team_id=$1 AND player_id=$2", (team_id, pid))

            # Auto-assign bench order for non-starters
            bench = await db.execute_fetchall(
                "SELECT player_id FROM team_players WHERE team_id=$1 AND is_starter=0 ORDER BY player_id",
                (team_id,),
            )
            for i, b in enumerate(bench):
                await db.execute(
                    "UPDATE team_players SET bench_order=$1 WHERE team_id=$2 AND player_id=$3",
                    (i + 1, team_id, b["player_id"]),
                )

        if body.captain:
            await db.execute("UPDATE team_players SET is_captain=0 WHERE team_id=$1", (team_id,))
            await db.execute("UPDATE team_players SET is_captain=1 WHERE team_id=$1 AND player_id=$2", (team_id, body.captain))

        if body.vice_captain:
            await db.execute("UPDATE team_players SET is_vice_captain=0 WHERE team_id=$1", (team_id,))
            await db.execute("UPDATE team_players SET is_vice_captain=1 WHERE team_id=$1 AND player_id=$2", (team_id, body.vice_captain))

        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


# --- Matchday-specific lineups ---

@router.get("/teams/{team_id}/matchday-lineup/{matchday_id}")
async def get_matchday_lineup(team_id: str, matchday_id: str, auth: dict = Depends(get_current_team)):
    """Get lineup for a specific matchday. Creates from defaults if not exists."""
    # Backfill any missing players from simulator
    from src.backend.config import settings
    if settings.SIMULATOR_API_URL:
        from src.backend.services.simulator_client import ensure_team_players_in_db
        await ensure_team_players_in_db(team_id)

    db = await get_db()
    try:
        # Check if matchday lineup exists
        existing = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM matchday_lineups WHERE team_id=$1 AND matchday_id=$2",
            (team_id, matchday_id),
        )
        if existing[0]["cnt"] == 0:
            # Ensure matchday row exists for FK integrity
            await _ensure_matchday_exists(db, matchday_id)
            # Copy from default team_players
            defaults = await db.execute_fetchall(
                "SELECT player_id, is_starter, is_captain, is_vice_captain FROM team_players WHERE team_id=$1",
                (team_id,),
            )
            for d in defaults:
                d = dict(d)
                await db.execute(
                    "INSERT INTO matchday_lineups (team_id, matchday_id, player_id, is_starter, is_captain, is_vice_captain) VALUES ($1,$2,$3,$4,$5,$6)",
                    (team_id, matchday_id, d["player_id"], d["is_starter"], d["is_captain"], d["is_vice_captain"]),
                )
            await db.commit()
        else:
            # Backfill: any new player added to team_players AFTER the lineup was
            # created (e.g. via reposition draft) won't have a matchday_lineups row
            # yet, so they wouldn't appear in the lineup UI. Insert them as bench.
            # Only for non-completed matchdays.
            md_status = await db.execute_fetchall(
                "SELECT status FROM matchdays WHERE id=$1", (matchday_id,)
            )
            is_completed = bool(md_status) and md_status[0]["status"] == "completed"
            if not is_completed:
                missing = await db.execute_fetchall(
                    """SELECT tp.player_id FROM team_players tp
                       LEFT JOIN matchday_lineups ml
                         ON ml.team_id = tp.team_id
                        AND ml.matchday_id = $1
                        AND ml.player_id = tp.player_id
                       WHERE tp.team_id = $2 AND ml.player_id IS NULL""",
                    (matchday_id, team_id),
                )
                if missing:
                    for m in missing:
                        await db.execute(
                            "INSERT INTO matchday_lineups (team_id, matchday_id, player_id, is_starter, is_captain, is_vice_captain) VALUES ($1,$2,$3,0,0,0) ON CONFLICT DO NOTHING",
                            (team_id, matchday_id, m["player_id"]),
                        )
                    await db.commit()

        # Fetch lineup with player details, matchday points, and avg points
        rows = await db.execute_fetchall(
            """SELECT ml.player_id, ml.is_starter, ml.is_captain, ml.is_vice_captain,
                      p.name, p.country_code, p.position, p.club, p.photo, p.market_value,
                      COALESCE(pts_all.total, 0) as total_points,
                      COALESCE(pts_all.avg_pts, 0) as avg_points,
                      COALESCE(pts_all.matches_played, 0) as matches_played,
                      COALESCE(pts_md.md_points, 0) as matchday_points,
                      COALESCE(pts_md.md_goals, 0) as matchday_goals,
                      COALESCE(pts_md.md_assists, 0) as matchday_assists,
                      COALESCE(pts_md.md_yellow, 0) as matchday_yellow_cards,
                      COALESCE(pts_md.md_red, 0) as matchday_red_card,
                      COALESCE(pts_md.md_minutes, 0) as matchday_minutes
               FROM matchday_lineups ml
               JOIN players p ON ml.player_id = p.id
               LEFT JOIN (
                   SELECT player_id, SUM(total_points) as total,
                          ROUND(AVG(total_points), 1) as avg_pts,
                          COUNT(*) as matches_played
                   FROM match_scores GROUP BY player_id
               ) pts_all ON pts_all.player_id = ml.player_id
               LEFT JOIN (
                   SELECT player_id,
                          SUM(total_points) as md_points,
                          SUM(goals) as md_goals,
                          SUM(assists) as md_assists,
                          SUM(yellow_cards) as md_yellow,
                          MAX(red_card) as md_red,
                          SUM(minutes_played) as md_minutes
                   FROM match_scores WHERE matchday_id=$1 GROUP BY player_id
               ) pts_md ON pts_md.player_id = ml.player_id
               WHERE ml.team_id=$2 AND ml.matchday_id=$3
               ORDER BY ml.is_starter DESC""",
            (matchday_id, team_id, matchday_id),
        )

        # Get match kickoff times to determine lock status
        # Get played countries from simulator + local matches
        from src.backend.services.lineup_service import _get_played_countries
        played_countries = await _get_played_countries(matchday_id)
        
        matches = await db.execute_fetchall(
            "SELECT home_country, away_country, status FROM matches WHERE matchday_id=$1",
            (matchday_id,),
        )
        for m in matches:
            m = dict(m)
            if m["status"] in ("live", "finished"):
                played_countries.add(m["home_country"])
                played_countries.add(m["away_country"])

        players = []
        for r in rows:
            r = dict(r)
            r["locked"] = r["country_code"] in played_countries
            players.append(r)

        return {"matchday_id": matchday_id, "team_id": team_id, "players": players}
    finally:
        await db.close()


@router.patch("/teams/{team_id}/matchday-lineup/{matchday_id}")
async def update_matchday_lineup(team_id: str, matchday_id: str, body: LineupUpdate, auth: dict = Depends(get_current_team)):
    """Update matchday-specific lineup with lock validation.
    
    Rules during active matchday:
    - Can remove ANY starter (played or not) → they lose their points
    - Can only ADD a starter whose country has NOT played yet
    - Can't change captain/VC to a player whose country already played
    - Bench players whose country already played are locked (can't touch)
    """
    if auth["team_id"] != team_id:
        raise HTTPException(403, "Not your team")

    # Get played countries from simulator (most reliable source)
    from src.backend.services.lineup_service import _get_played_countries
    played_countries = await _get_played_countries(matchday_id)
    
    # Also check local matches as fallback
    db = await get_db()
    try:
        matches = await db.execute_fetchall(
            "SELECT home_country, away_country, status FROM matches WHERE matchday_id=$1",
            (matchday_id,),
        )
        for m in matches:
            m = dict(m)
            if m["status"] in ("live", "finished"):
                played_countries.add(m["home_country"])
                played_countries.add(m["away_country"])
        
        matchday_started = len(played_countries) > 0

        # Ensure matchday lineup exists
        existing = await db.execute_fetchall(
            "SELECT COUNT(*) as cnt FROM matchday_lineups WHERE team_id=$1 AND matchday_id=$2",
            (team_id, matchday_id),
        )
        if existing[0]["cnt"] == 0:
            # Ensure matchday row exists for FK integrity
            await _ensure_matchday_exists(db, matchday_id)
            # Copy defaults first
            defaults = await db.execute_fetchall(
                "SELECT player_id, is_starter, is_captain, is_vice_captain FROM team_players WHERE team_id=$1",
                (team_id,),
            )
            for d in defaults:
                d = dict(d)
                await db.execute(
                    "INSERT INTO matchday_lineups (team_id, matchday_id, player_id, is_starter, is_captain, is_vice_captain) VALUES ($1,$2,$3,$4,$5,$6)",
                    (team_id, matchday_id, d["player_id"], d["is_starter"], d["is_captain"], d["is_vice_captain"]),
                )

        if body.starters is not None:
            if len(body.starters) != 11:
                raise HTTPException(400, "La alineación debe tener exactamente 11 titulares")

            # Validate formation limits (1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD)
            placeholders = ",".join(f"${i+1}" for i in range(len(body.starters)))
            pos_rows = await db.execute_fetchall(
                f"SELECT position FROM players WHERE id IN ({placeholders})",
                list(body.starters),
            )
            pos_counts = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
            for r in pos_rows:
                pos = dict(r)["position"]
                if pos in pos_counts:
                    pos_counts[pos] += 1
            POS_LIMITS = {"GK": (1, 1), "DEF": (3, 5), "MID": (2, 5), "FWD": (1, 3)}
            POS_LABELS = {"GK": "porteros", "DEF": "defensas", "MID": "centrocampistas", "FWD": "delanteros"}
            for pos, (mn, mx) in POS_LIMITS.items():
                c = pos_counts[pos]
                if c < mn:
                    raise HTTPException(400, f"Mínimo {mn} {POS_LABELS[pos]} (tienes {c})")
                if c > mx:
                    raise HTTPException(400, f"Máximo {mx} {POS_LABELS[pos]} (tienes {c})")

            # Validate: can't ADD a locked player as starter (their match started)
            current_starters = await db.execute_fetchall(
                "SELECT ml.player_id FROM matchday_lineups ml WHERE ml.team_id=$1 AND ml.matchday_id=$2 AND ml.is_starter=1",
                (team_id, matchday_id),
            )
            current_starter_ids = {dict(r)["player_id"] for r in current_starters}
            new_starters = set(body.starters)

            # Players being promoted from bench to starter
            promoted = new_starters - current_starter_ids
            for pid in promoted:
                player = await db.execute_fetchall("SELECT country_code FROM players WHERE id=$1", (pid,))
                if player and dict(player[0])["country_code"] in played_countries:
                    pname = await db.execute_fetchall("SELECT name FROM players WHERE id=$1", (pid,))
                    name = dict(pname[0])["name"] if pname else pid
                    raise HTTPException(409, f"No puedes titular a {name}: su partido ya ha empezado")

            # Note: demoting a played starter IS allowed — they simply lose their points
            # for this matchday (final scoring uses current is_starter), enabling swaps
            # like "benched player whose match is done → fresh bench player not yet played".

            # Update lineup
            await db.execute(
                "UPDATE matchday_lineups SET is_starter=0 WHERE team_id=$1 AND matchday_id=$2",
                (team_id, matchday_id),
            )
            for pid in body.starters:
                await db.execute(
                    "UPDATE matchday_lineups SET is_starter=1 WHERE team_id=$1 AND matchday_id=$2 AND player_id=$3",
                    (team_id, matchday_id, pid),
                )

        if body.captain:
            # Can't set captain if locked
            cp = await db.execute_fetchall("SELECT country_code FROM players WHERE id=$1", (body.captain,))
            if cp and dict(cp[0])["country_code"] in played_countries:
                raise HTTPException(409, "No puedes cambiar el capitán: su partido ya ha empezado")
            await db.execute("UPDATE matchday_lineups SET is_captain=0 WHERE team_id=$1 AND matchday_id=$2", (team_id, matchday_id))
            await db.execute("UPDATE matchday_lineups SET is_captain=1 WHERE team_id=$1 AND matchday_id=$2 AND player_id=$3", (team_id, matchday_id, body.captain))

        if body.vice_captain:
            vcp = await db.execute_fetchall("SELECT country_code FROM players WHERE id=$1", (body.vice_captain,))
            if vcp and dict(vcp[0])["country_code"] in played_countries:
                raise HTTPException(409, "No puedes cambiar el vice-capitán: su partido ya ha empezado")
            await db.execute("UPDATE matchday_lineups SET is_vice_captain=0 WHERE team_id=$1 AND matchday_id=$2", (team_id, matchday_id))
            await db.execute("UPDATE matchday_lineups SET is_vice_captain=1 WHERE team_id=$1 AND matchday_id=$2 AND player_id=$3", (team_id, matchday_id, body.vice_captain))

        await db.commit()
        return {"ok": True}
    except HTTPException:
        try:
            await db.rollback()
        except Exception:
            pass
        raise
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        tb = traceback.format_exc()
        logger.error(
            f"update_matchday_lineup failed team_id={team_id} matchday_id={matchday_id} "
            f"starters={body.starters} captain={body.captain} vice={body.vice_captain}\n{tb}"
        )
        raise HTTPException(500, f"Error guardando alineación: {type(e).__name__}: {e}")
    finally:
        await db.close()


# --- NEW: 5-player lineup endpoints ---

@router.get("/teams/{team_id}/lineup-5/{matchday_id}")
async def get_5_player_lineup(team_id: str, matchday_id: str, auth: dict = Depends(get_current_team)):
    """Get 5-player lineup status for a matchday (before/during/after)."""
    if auth["team_id"] != team_id:
        raise HTTPException(403, "Not your team")
    
    from src.backend.services.lineup_service import get_played_countries, ensure_matchday_snapshot
    
    played_countries = await get_played_countries(matchday_id)
    matchday_started = len(played_countries) > 0
    # Always ensure snapshot so pre-matchday lineup editor has full squad rows.
    await ensure_matchday_snapshot(team_id, matchday_id)
    
    db = await get_db()
    try:
        lineup = await db.execute_fetchall(
            """SELECT ml.player_id, ml.is_starter, ml.is_captain, ml.is_vice_captain, ml.is_wildcard, ml.position_slot,
                      p.name, p.country_code, p.position, p.photo, p.club,
                      COALESCE(ms.total_points, 0) as matchday_points, COALESCE(ms.minutes_played, 0) as matchday_minutes,
                      COALESCE(pts_all.total_points, 0) as total_points
               FROM matchday_lineups ml
               JOIN players p ON ml.player_id = p.id
               LEFT JOIN match_scores ms ON ms.player_id = ml.player_id AND ms.matchday_id = $1
               LEFT JOIN (
                   SELECT player_id, SUM(total_points) as total_points
                   FROM match_scores
                   GROUP BY player_id
               ) pts_all ON pts_all.player_id = ml.player_id
               WHERE ml.team_id=$2 AND ml.matchday_id=$3
               ORDER BY ml.is_starter DESC, ml.position_slot""",
            (matchday_id, team_id, matchday_id)
        )
        
        if not lineup:
            return {
                "matchday_id": matchday_id, "started": False, "played_countries": [],
                "starters": {}, "bench": [], "captain_id": None, "vice_captain_id": None,
            }
        
        starters = {}
        bench = []
        captain_id = None
        vice_captain_id = None
        
        for p in lineup:
            p = dict(p)
            player_info = {
                "player_id": p["player_id"], "name": p["name"], "country_code": p["country_code"],
                "position": p["position"], "photo": p["photo"], "club": p["club"],
                "matchday_points": p["matchday_points"], "matchday_minutes": p["matchday_minutes"],
                "total_points": p["total_points"],
                "country_played": p["country_code"] in played_countries,
                "is_captain": p["is_captain"], "is_vice_captain": p["is_vice_captain"],
            }
            
            if p["is_starter"]:
                starters[p["position_slot"]] = player_info
                if p["is_captain"]:
                    captain_id = p["player_id"]
                if p["is_vice_captain"]:
                    vice_captain_id = p["player_id"]
            else:
                bench.append(player_info)
        
        return {
            "matchday_id": matchday_id, "started": matchday_started,
            "played_countries": sorted(played_countries), "starters": starters,
            "bench": bench, "captain_id": captain_id, "vice_captain_id": vice_captain_id,
        }
    finally:
        await db.close()


@router.patch("/teams/{team_id}/lineup-5/{matchday_id}")
async def update_5_player_lineup(team_id: str, matchday_id: str, body: dict, auth: dict = Depends(get_current_team)):
    """Update 5-player lineup with validation.
    
    body = {
        'GK': player_id,
        'DEF': player_id,
        'MID': player_id,
        'FWD': player_id,
        'WILDCARD': player_id,
        'captain_id': player_id (optional),
        'vice_captain_id': player_id (optional)
    }
    """
    if auth["team_id"] != team_id:
        raise HTTPException(403, "Not your team")
    
    from src.backend.services.lineup_service import (
        validate_5_player_lineup, ensure_matchday_snapshot, get_played_countries
    )
    
    # Extract captain info
    captain_id = body.pop('captain_id', None)
    vice_captain_id = body.pop('vice_captain_id', None)
    
    # Validate lineup structure
    is_valid, msg = await validate_5_player_lineup(team_id, body)
    if not is_valid:
        raise HTTPException(400, msg)
    
    db = await get_db()
    try:
        # Ensure matchday exists
        await _ensure_matchday_exists(db, matchday_id)
        await ensure_matchday_snapshot(team_id, matchday_id)

        # Allow edits during active matchday, but not when completed.
        md = await db.execute_fetchall("SELECT status FROM matchdays WHERE id=$1", (matchday_id,))
        md_status = dict(md[0])["status"] if md else "upcoming"
        if md_status == "completed":
            raise HTTPException(409, "Cannot change lineup: matchday already completed")

        played_countries = await get_played_countries(matchday_id)

        # Fetch current starters to validate promotions from bench -> starter.
        current_rows = await db.execute_fetchall(
            "SELECT player_id, is_starter FROM matchday_lineups WHERE team_id=$1 AND matchday_id=$2",
            (team_id, matchday_id),
        )
        current_starters = {dict(r)["player_id"] for r in current_rows if dict(r)["is_starter"]}
        new_starters = set(body.values())
        promoted = new_starters - current_starters

        if promoted and played_countries:
            placeholders = ",".join(f"${i+1}" for i in range(len(promoted)))
            promoted_rows = await db.execute_fetchall(
                f"SELECT id, name, country_code FROM players WHERE id IN ({placeholders})",
                list(promoted),
            )
            for row in promoted_rows:
                p = dict(row)
                if p["country_code"] in played_countries:
                    raise HTTPException(409, f"No puedes titular a {p['name']}: su partido ya ha empezado")
        
        # Clear current starters but keep the snapshot rows.
        await db.execute(
            "UPDATE matchday_lineups SET is_starter=0, is_wildcard=0, position_slot=NULL WHERE team_id=$1 AND matchday_id=$2",
            (team_id, matchday_id),
        )

        # Upsert the 5 selected slots so a missing snapshot row cannot silently drop the save.
        for slot, player_id in body.items():
            is_wildcard = 1 if slot == "WILDCARD" else 0
            is_cap = 1 if player_id == captain_id else 0
            is_vc = 1 if player_id == vice_captain_id else 0
            await db.execute(
                """INSERT INTO matchday_lineups
                   (team_id, matchday_id, player_id, is_starter, is_captain, is_vice_captain, is_wildcard, position_slot)
                   VALUES ($1,$2,$3,1,$4,$5,$6,$7)
                   ON CONFLICT(team_id, matchday_id, player_id) DO UPDATE SET
                     is_starter=1,
                     is_captain=excluded.is_captain,
                     is_vice_captain=excluded.is_vice_captain,
                     is_wildcard=excluded.is_wildcard,
                     position_slot=excluded.position_slot""",
                (team_id, matchday_id, player_id, is_cap, is_vc, is_wildcard, slot),
            )
        
        await db.commit()
        return {"ok": True, "message": "Lineup saved", "captain_id": captain_id, "vice_captain_id": vice_captain_id}
    except Exception as e:
        try:
            await db.rollback()
        except:
            pass
        logger.error(f"update_5_player_lineup failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"Error: {e}")
    finally:
        await db.close()


@router.post("/teams/{team_id}/matchday/{matchday_id}/in-game-sub")
async def perform_in_game_substitution(team_id: str, matchday_id: str, body: dict, auth: dict = Depends(get_current_team)):
    """Perform mid-matchday substitution (swap played OUT ↔ unplayed IN).
    
    body = {
        'player_out_id': str,   # Already played
        'player_in_id': str     # Haven't played yet
    }
    
    Rules:
    ✅ player_out must have already played (minutes_played > 0)
    ✅ player_in must NOT have played yet (minutes_played = 0 or no row)
    ✅ Both players in team's current lineup
    """
    if auth["team_id"] != team_id:
        raise HTTPException(403, "Not your team")
    
    from src.backend.services.lineup_service import can_perform_substitution
    
    player_out = body.get("player_out_id")
    player_in = body.get("player_in_id")
    
    if not player_out or not player_in:
        raise HTTPException(400, "Missing player_out_id or player_in_id")
    
    is_valid, msg = await can_perform_substitution(team_id, matchday_id, player_out, player_in)
    if not is_valid:
        raise HTTPException(400, msg)
    
    db = await get_db()
    try:
        # Get OUT slot info
        out_slot = await db.execute_fetchall(
            """SELECT position_slot, is_wildcard FROM matchday_lineups 
               WHERE team_id=$1 AND matchday_id=$2 AND player_id=$3 AND is_starter=1""",
            (team_id, matchday_id, player_out)
        )
        
        if not out_slot:
            raise HTTPException(400, f"Player {player_out} not in current starters")
        
        slot_info = dict(out_slot[0])
        out_slot_name = slot_info["position_slot"]
        is_wildcard = slot_info["is_wildcard"]
        
        # Perform swap: OUT player to bench
        await db.execute(
            """UPDATE matchday_lineups SET is_starter=0, is_wildcard=0, position_slot=NULL 
               WHERE team_id=$1 AND matchday_id=$2 AND player_id=$3""",
            (team_id, matchday_id, player_out)
        )
        
        # IN player to starter in same slot
        await db.execute(
            """UPDATE matchday_lineups SET is_starter=1, is_wildcard=$1, position_slot=$2 
               WHERE team_id=$3 AND matchday_id=$4 AND player_id=$5""",
            (is_wildcard, out_slot_name, team_id, matchday_id, player_in)
        )
        
        # Log substitution
        await db.execute(
            """INSERT INTO in_game_substitutions (team_id, matchday_id, player_out_id, player_in_id, created_at)
               VALUES ($1, $2, $3, $4, $5)""",
            (team_id, matchday_id, player_out, player_in, datetime.now(timezone.utc).isoformat())
        )
        
        await db.commit()
        
        logger.info(f"In-game sub: team {team_id} md {matchday_id}: {player_out} → bench, {player_in} → starter")
        
        return {
            "ok": True,
            "message": f"Substitution done",
            "out": player_out,
            "in": player_in,
            "slot": out_slot_name,
        }
    except Exception as e:
        try:
            await db.rollback()
        except:
            pass
        logger.error(f"perform_in_game_substitution failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"Error: {e}")
    finally:
        await db.close()
