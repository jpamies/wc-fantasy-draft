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
                await db.execute("DELETE FROM match_scores WHERE match_id = ?", (stale_id,))
                await db.execute("DELETE FROM matches WHERE id = ?", (stale_id,))
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
                   VALUES (?, ?, ?, ?, 'active')
                   ON CONFLICT(id) DO UPDATE SET status = 'active'""",
                (matchday_id, matchday_id, match.get("kickoff", ""), "group_stage"),
            )
            
            # Insert match result (IGNORE if already exists — don't overwrite)
            await db.execute(
                """INSERT OR IGNORE INTO matches (id, matchday_id, home_country, away_country,
                   kickoff, score_home, score_away, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'finished')""",
                (match_id, matchday_id, match.get("home_code", ""),
                 match.get("away_code", ""), match.get("kickoff", ""),
                 match.get("score_home"), match.get("score_away")),
            )
            
            # Insert player scores (IGNORE if already exists — never overwrite user data)
            for s in stats:
                player_id = s.get("player_id", "")
                position = s.get("position", "MID")
                points = calculate_player_points(s, position)
                
                # Ensure player exists in local DB (FK)
                await db.execute(
                    """INSERT OR IGNORE INTO players (id, name, country_code, position, market_value)
                       VALUES (?, ?, ?, ?, 0)""",
                    (player_id, s.get("player_name", ""), s.get("country_code", ""), position),
                )
                
                # Ensure country exists
                await db.execute(
                    "INSERT OR IGNORE INTO countries (code, name) VALUES (?, ?)",
                    (s.get("country_code", ""), s.get("country_code", "")),
                )
                
                # INSERT OR IGNORE: only insert new scores, never overwrite
                await db.execute(
                    """INSERT OR IGNORE INTO match_scores
                       (player_id, matchday_id, match_id, minutes_played, goals, assists,
                        clean_sheet, yellow_cards, red_card, own_goals, penalties_missed,
                        penalties_saved, saves, goals_conceded, rating, total_points)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            "INSERT OR REPLACE INTO sync_state (key, value) VALUES ('last_sync', ?)",
            (datetime.utcnow().isoformat(),),
        )
        await db.commit()
        
        logger.info(f"Synced {len(new_matches)} matches, {total_scores} scores, {teams_scored} team scores, removed {removed}")
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
                    """INSERT OR REPLACE INTO sync_state (key, value)
                       VALUES (?, ?)""",
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
