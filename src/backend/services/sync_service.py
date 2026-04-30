"""Sync service — polls simulator for finished matches and calculates fantasy points."""

import json
import logging
from datetime import datetime

from src.backend.database import get_db
from src.backend.config import settings

logger = logging.getLogger("wc-fantasy.sync")

# Fantasy scoring formula
POINTS = {
    "minutes_played_any": 1,      # Played at all
    "minutes_played_60": 1,       # Played 60+ minutes
    "goal_fwd": 4,
    "goal_mid": 5,
    "goal_def": 6,
    "goal_gk": 6,
    "assist": 3,
    "clean_sheet_gk": 4,          # GK/DEF, 60+ min
    "clean_sheet_def": 4,
    "saves_per_3": 1,             # Every 3 saves (GK)
    "penalty_missed": -2,
    "yellow_card": -1,
    "red_card": -3,
    "own_goal": -2,
    "goals_conceded_per_2": -1,   # GK/DEF, every 2 goals conceded
    "mvp_bonus": 3,               # Rating >= 8.0
}


def calculate_player_points(stat: dict, position: str) -> int:
    """Calculate fantasy points for a player based on match stats."""
    pts = 0
    minutes = stat.get("minutes_played", 0) or 0
    
    if minutes <= 0:
        return 0
    
    # Appearance
    pts += POINTS["minutes_played_any"]
    if minutes >= 60:
        pts += POINTS["minutes_played_60"]
    
    # Goals
    goals = stat.get("goals", 0) or 0
    if goals > 0:
        goal_key = f"goal_{position.lower()}" if f"goal_{position.lower()}" in POINTS else "goal_mid"
        pts += goals * POINTS.get(goal_key, 4)
    
    # Assists
    assists = stat.get("assists", 0) or 0
    pts += assists * POINTS["assist"]
    
    # Clean sheet (GK/DEF, 60+ min)
    clean_sheet = stat.get("clean_sheet", False)
    if clean_sheet and minutes >= 60:
        if position == "GK":
            pts += POINTS["clean_sheet_gk"]
        elif position == "DEF":
            pts += POINTS["clean_sheet_def"]
    
    # GK saves
    if position == "GK":
        saves = stat.get("saves", 0) or 0
        pts += (saves // 3) * POINTS["saves_per_3"]
    
    # Penalties missed
    pens_missed = stat.get("penalties_missed", 0) or 0
    pts += pens_missed * POINTS["penalty_missed"]
    
    # Cards
    yellows = stat.get("yellow_cards", 0) or 0
    pts += yellows * POINTS["yellow_card"]
    
    red = stat.get("red_card", False)
    if red:
        pts += POINTS["red_card"]
    
    # Own goals
    own_goals = stat.get("own_goals", 0) or 0
    pts += own_goals * POINTS["own_goal"]
    
    # Goals conceded (GK/DEF)
    if position in ("GK", "DEF") and minutes >= 60:
        gc = stat.get("goals_conceded", 0) or 0
        pts += (gc // 2) * POINTS["goals_conceded_per_2"]
    
    # MVP bonus
    rating = stat.get("rating", 0) or 0
    if rating >= 8.0:
        pts += POINTS["mvp_bonus"]
    
    return pts


async def sync_results() -> dict:
    """Poll simulator for finished matches and sync scores to fantasy DB.
    
    Returns summary of what was synced.
    """
    if not settings.SIMULATOR_API_URL:
        return {"error": "SIMULATOR_API_URL not configured"}
    
    import httpx
    
    db = await get_db()
    try:
        # Get list of match IDs already synced
        synced = await db.execute_fetchall(
            "SELECT DISTINCT match_id FROM match_scores WHERE match_id IS NOT NULL"
        )
        synced_ids = {r["match_id"] for r in synced}
        
        # Fetch all finished matches with stats from simulator
        async with httpx.AsyncClient(
            base_url=settings.SIMULATOR_API_URL.rstrip("/"),
            timeout=30.0,
        ) as client:
            resp = await client.get("/api/v1/matches/finished-with-stats")
            resp.raise_for_status()
            finished = resp.json()
        
        finished_ids = {m["match"]["id"] for m in finished} if finished else set()
        
        # Detect reset: if we have synced matches that no longer exist in simulator
        stale_ids = synced_ids - finished_ids
        removed = 0
        if stale_ids:
            for stale_id in stale_ids:
                await db.execute("DELETE FROM match_scores WHERE match_id = $1", (stale_id,))
                await db.execute("DELETE FROM matches WHERE id = $1", (stale_id,))
            await db.commit()
            removed = len(stale_ids)
            logger.info(f"Removed {removed} stale matches (simulator reset detected)")
            synced_ids -= stale_ids
        
        if not finished:
            return {"synced": 0, "removed": removed, "message": "No finished matches in simulator"}
        
        # Filter to only new matches
        new_matches = [m for m in finished if m["match"]["id"] not in synced_ids]
        
        if not new_matches and removed == 0:
            # No new matches, but still recalculate team points (handles mid-matchday swaps)
            active_mds = await db.execute_fetchall(
                "SELECT id FROM matchdays WHERE status = 'active'"
            )
            if active_mds:
                teams_scored = await _update_team_points([m["id"] for m in active_mds])
            else:
                teams_scored = 0
            return {"synced": 0, "already_synced": len(synced_ids), "teams_recalculated": teams_scored, "message": "All up to date, team points recalculated"}
        
        # Ensure lineup snapshots exist for all teams in affected matchdays
        new_matchday_ids = list({e["match"]["matchday_id"] for e in new_matches})
        await _ensure_all_snapshots(new_matchday_ids)
        
        # Insert NEW match scores only (don't touch existing ones)
        total_scores = 0
        for entry in new_matches:
            match = entry["match"]
            stats = entry["stats"]
            match_id = match["id"]
            matchday_id = match["matchday_id"]
            
            # Upsert matchday (mark as active once it has results)
            await db.execute(
                """INSERT INTO matchdays (id, name, date, phase, status)
                   VALUES ($1, $2, $3, $4, 'active')
                   ON CONFLICT(id) DO UPDATE SET status = 'active'""",
                (matchday_id, matchday_id, match.get("kickoff", ""), "group_stage"),
            )
            
            # Ensure both countries exist for the match FK
            home_code = match.get("home_code", "")
            away_code = match.get("away_code", "")
            if home_code:
                await db.execute(
                    "INSERT INTO countries (code, name) VALUES ($1, $2) ON CONFLICT (code) DO NOTHING",
                    (home_code, match.get("home_team", home_code)),
                )
            if away_code:
                await db.execute(
                    "INSERT INTO countries (code, name) VALUES ($1, $2) ON CONFLICT (code) DO NOTHING",
                    (away_code, match.get("away_team", away_code)),
                )
            
            # Insert match result (IGNORE if already exists — don't overwrite)
            await db.execute(
                """INSERT INTO matches (id, matchday_id, home_country, away_country,
                   kickoff, score_home, score_away, status)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, 'finished') ON CONFLICT (id) DO NOTHING""",
                (match_id, matchday_id, home_code,
                 away_code, match.get("kickoff", ""),
                 match.get("score_home"), match.get("score_away")),
            )
            
            # Insert player scores (IGNORE if already exists — never overwrite user data)
            for s in stats:
                player_id = s.get("player_id", "")
                position = s.get("position", "MID")
                points = calculate_player_points(s, position)
                
                # Ensure country exists FIRST (player has FK to country)
                await db.execute(
                    "INSERT INTO countries (code, name) VALUES ($1, $2) ON CONFLICT (code) DO NOTHING",
                    (s.get("country_code", ""), s.get("country_code", "")),
                )
                
                # Ensure player exists in local DB (FK to countries)
                await db.execute(
                    """INSERT INTO players (id, name, country_code, position, market_value)
                       VALUES ($1, $2, $3, $4, 0)
                       ON CONFLICT (id) DO NOTHING""",
                    (player_id, s.get("player_name", ""), s.get("country_code", ""), position),
                )
                
                # INSERT OR IGNORE: only insert new scores, never overwrite
                await db.execute(
                    """INSERT INTO match_scores
                       (player_id, matchday_id, match_id, minutes_played, goals, assists,
                        clean_sheet, yellow_cards, red_card, own_goals, penalties_missed,
                        penalties_saved, saves, goals_conceded, rating, total_points)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                       ON CONFLICT (player_id, matchday_id) DO NOTHING""",
                    (player_id, matchday_id, match_id,
                     s.get("minutes_played", 0), s.get("goals", 0), s.get("assists", 0),
                     1 if s.get("clean_sheet") else 0,
                     s.get("yellow_cards", 0), 1 if s.get("red_card") else 0,
                     s.get("own_goals", 0), s.get("penalties_missed", 0),
                     s.get("penalties_saved", 0), s.get("saves", 0),
                     s.get("goals_conceded", 0), s.get("rating", 0),
                     points),
                )
                total_scores += 1
        
        await db.commit()
        
        # ALWAYS recalculate team points for ALL active matchdays (handles mid-matchday swaps)
        active_mds = await db.execute_fetchall(
            "SELECT id FROM matchdays WHERE status = 'active'"
        )
        all_active_md_ids = [m["id"] for m in active_mds]
        teams_scored = await _update_team_points(all_active_md_ids)
        
        # Update sync state
        await db.execute(
            "INSERT INTO sync_state (key, value) VALUES ('last_sync', $1) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
            (datetime.utcnow().isoformat(),),
        )
        await db.commit()
        
        logger.info(f"Synced {len(new_matches)} matches, {total_scores} scores, {teams_scored} team scores, removed {removed}")

        # Sync country tournament status (alive / eliminated / champion)
        try:
            status_result = await sync_country_tournament_status()
            logger.info(f"Country status sync: {status_result}")
        except Exception as e:
            logger.warning(f"Country status sync skipped: {e}")

        return {
            "synced_matches": len(new_matches),
            "synced_scores": total_scores,
            "teams_scored": teams_scored,
            "removed_matches": removed,
            "already_synced": len(synced_ids),
            "total_finished": len(finished),
        }
    except Exception as e:
        logger.error(f"Sync error: {e}")
        return {"error": str(e)}
    finally:
        await db.close()


async def _update_team_points(matchday_ids: list[str]) -> int:
    """Recalculate fantasy team points for given matchdays.
    Uses existing ScoringEngine which handles lineups, auto-subs, captain bonus."""
    from src.backend.services.scoring_engine import ScoringEngine
    
    db = await get_db()
    try:
        # Get all fantasy teams across all leagues
        teams = await db.execute_fetchall("SELECT id, league_id FROM fantasy_teams")
        
        count = 0
        for team in teams:
            for md_id in matchday_ids:
                pts = await ScoringEngine.get_team_matchday_points(team["id"], md_id)
                # Store calculated points (for leaderboard queries)
                await db.execute(
                    """INSERT INTO sync_state (key, value)
                       VALUES ($1, $2)
                       ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value""",
                    (f"team_pts:{team['id']}:{md_id}", str(pts)),
                )
                count += 1
        
        await db.commit()
        return count
    finally:
        await db.close()


async def _ensure_all_snapshots(matchday_ids: list[str]):
    """Create lineup snapshots for all fantasy teams for the given matchdays.
    Only creates if no snapshot exists yet (first match of matchday finished)."""
    from src.backend.services.lineup_service import ensure_matchday_snapshot
    
    db = await get_db()
    try:
        teams = await db.execute_fetchall("SELECT id FROM fantasy_teams")
    finally:
        await db.close()
    
    for team in teams:
        for md_id in matchday_ids:
            await ensure_matchday_snapshot(team["id"], md_id)


# --------------- Country tournament-status sync ---------------

# Group-stage matchday IDs (3 rounds of group play)
_GROUP_MATCHDAYS = {"GS1", "GS2", "GS3"}

# Knockout phases in order
_KNOCKOUT_PHASES = ["r32", "r16", "quarter", "semi", "final"]


async def sync_country_tournament_status() -> dict:
    """Determine which countries are alive / eliminated / champion and persist
    the result in ``countries.tournament_status``.

    Logic
    -----
    1. **Groups not complete** → everyone is ``alive``.
    2. **Groups just completed** → top 2 per group + best 8 third-place teams
       are ``alive``; the rest are ``eliminated``.
    3. **Knockout** → the calendar tells us which countries are in
       scheduled/live knockout matches (alive).  Countries that lost a
       *finished* knockout match are ``eliminated``.
    4. If the final is finished, the winner is ``champion``.

    We derive everything from the simulator's ``/tournament/calendar``,
    ``/tournament/standings`` and ``/tournament/overview``.
    """
    from src.backend.services.simulator_client import (
        fetch_calendar,
        fetch_standings,
        fetch_tournament_overview,
    )

    overview = await fetch_tournament_overview()
    current_phase = overview.get("current_phase", "groups")

    # --- Collect all matches from the calendar ---------------------------------
    calendar = await fetch_calendar()            # list of matchday dicts
    all_matches: list[dict] = []
    gs_matchday_ids_with_matches: set[str] = set()  # GS matchdays that exist
    for md in calendar:
        md_id = md.get("id") or md.get("matchday_id") or ""
        for m in md.get("matches", []):
            m["_md_id"] = md_id
            all_matches.append(m)
        if md_id in _GROUP_MATCHDAYS:
            gs_matchday_ids_with_matches.add(md_id)

    # Are all group-stage matchdays fully finished?
    gs_matches = [m for m in all_matches if m["_md_id"] in _GROUP_MATCHDAYS]
    groups_complete = (
        len(gs_matches) > 0
        and all(m.get("status") == "finished" for m in gs_matches)
    )

    # --- Phase 1: groups not done → everyone alive ----------------------------
    if not groups_complete or current_phase == "groups":
        db = await get_db()
        try:
            await db.execute("UPDATE countries SET tournament_status = 'alive'")
            await db.commit()
        finally:
            await db.close()
        return {"phase": "groups", "alive": "all"}

    # --- Phase 2+: groups done → compute who qualifies / is eliminated --------

    # 2a. Get standings to find qualified countries from groups
    standings = await fetch_standings()
    qualified_from_groups: set[str] = set()

    # Top 2 per group always qualify
    for group, teams in standings.items():
        for t in teams[:2]:
            cc = t.get("country_code", "")
            if cc:
                qualified_from_groups.add(cc)

    # Best 8 third-place teams
    thirds: list[dict] = []
    for group, teams in standings.items():
        if len(teams) >= 3:
            thirds.append(teams[2])
    thirds.sort(
        key=lambda t: (
            t.get("points", 0),
            t.get("goals_for", 0) - t.get("goals_against", 0),
            t.get("goals_for", 0),
        ),
        reverse=True,
    )
    for t in thirds[:8]:
        cc = t.get("country_code", "")
        if cc:
            qualified_from_groups.add(cc)

    # 2b. From knockout matches, figure out alive vs eliminated
    knockout_matches = [
        m for m in all_matches if m["_md_id"] not in _GROUP_MATCHDAYS
    ]

    # Countries appearing in any scheduled/live knockout match are alive
    alive_in_knockout: set[str] = set()
    eliminated_in_knockout: set[str] = set()

    for m in knockout_matches:
        status = m.get("status", "")
        home = m.get("home_code") or ""
        away = m.get("away_code") or ""

        if status in ("scheduled", "live"):
            if home:
                alive_in_knockout.add(home)
            if away:
                alive_in_knockout.add(away)
        elif status == "finished" and home and away:
            # Determine loser → eliminated
            sh = m.get("score_home")
            sa = m.get("score_away")
            ph = m.get("penalty_home")
            pa = m.get("penalty_away")
            winner = None
            if sh is not None and sa is not None:
                if sh > sa:
                    winner = home
                elif sa > sh:
                    winner = away
                elif ph is not None and pa is not None:
                    winner = home if ph > pa else away
            if winner:
                loser = away if winner == home else home
                eliminated_in_knockout.add(loser)
                # Winner is alive unless eliminated in a LATER round
                alive_in_knockout.add(winner)

    # Remove anyone eliminated in knockout from alive
    alive_in_knockout -= eliminated_in_knockout

    # Final alive set: qualified from groups ∩ not eliminated in knockout
    # + anyone still in a scheduled/live knockout match
    alive: set[str] = set()
    for cc in qualified_from_groups:
        if cc not in eliminated_in_knockout:
            alive.add(cc)
    alive |= alive_in_knockout

    # Special case: detect champion (tournament completed)
    champion: str | None = None
    if current_phase == "completed":
        final_matches = [m for m in knockout_matches if m["_md_id"].upper() == "FINAL"]
        for m in final_matches:
            # The real final (not 3rd-place match) — try to identify
            sh = m.get("score_home")
            sa = m.get("score_away")
            home = m.get("home_code", "")
            away = m.get("away_code", "")
            if sh is not None and sa is not None and home and away:
                if sh > sa:
                    champion = home
                elif sa > sh:
                    champion = away
                else:
                    ph = m.get("penalty_home")
                    pa = m.get("penalty_away")
                    if ph is not None and pa is not None:
                        champion = home if ph > pa else away

    # --- Persist ---------------------------------------------------------------
    db = await get_db()
    try:
        # Default everything to eliminated
        await db.execute("UPDATE countries SET tournament_status = 'eliminated'")

        if alive:
            placeholders = ",".join(f"${i+1}" for i in range(len(alive)))
            await db.execute(
                f"UPDATE countries SET tournament_status = 'alive' WHERE code IN ({placeholders})",
                list(alive),
            )

        if champion:
            await db.execute(
                "UPDATE countries SET tournament_status = 'champion' WHERE code = $1",
                (champion,),
            )

        await db.commit()
    finally:
        await db.close()

    return {
        "phase": current_phase,
        "alive": len(alive),
        "eliminated": len(qualified_from_groups | {cc for cc in eliminated_in_knockout}) - len(alive),
        "champion": champion,
    }
