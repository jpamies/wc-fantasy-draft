"""Scoring engine — calculate points per player/matchday per SCORING.md rules."""

from src.backend.database import get_db


def calculate_points(position: str, minutes: int, goals: int, assists: int,
                     yellow_cards: int, red_card: bool, own_goals: int,
                     penalties_missed: int, penalties_saved: int, saves: int,
                     goals_conceded: int, clean_sheet: bool, rating: float,
                     is_mvp: bool) -> int:
    pts = 0

    # Participation
    if minutes >= 60:
        pts += 2
    elif minutes > 0:
        pts += 1
    else:
        return 0  # No participation = 0 points

    # Goals by position
    goal_pts = {"GK": 6, "DEF": 6, "MID": 5, "FWD": 4}
    pts += goals * goal_pts.get(position, 4)

    # Assists
    pts += assists * 3

    # Clean sheet (only if played >= 60 min)
    if clean_sheet and minutes >= 60:
        if position in ("GK", "DEF"):
            pts += 4
        elif position == "MID":
            pts += 1

    # Goals conceded (GK/DEF, >= 60 min)
    if position in ("GK", "DEF") and minutes >= 60:
        pts -= (goals_conceded // 2)

    # Penalties
    pts -= penalties_missed * 2
    if position == "GK":
        pts += penalties_saved * 5
        pts += saves // 3  # Every 3 saves = 1 point

    # Discipline
    pts -= yellow_cards
    if red_card:
        pts -= 3

    # Own goals
    pts -= own_goals * 2

    # Bonus
    if is_mvp:
        pts += 3
    if goals >= 3:  # Hat-trick bonus
        pts += 3

    return pts


class ScoringEngine:

    @staticmethod
    async def process_match_scores(matchday_id: str, match_id: str, scores: list[dict]) -> list[dict]:
        db = await get_db()
        try:
            # Get match to determine clean sheets
            match_row = await db.execute_fetchall("SELECT * FROM matches WHERE id=$1", (match_id,))
            match_info = dict(match_row[0]) if match_row else {}

            home_conceded = match_info.get("score_away", 0) or 0
            away_conceded = match_info.get("score_home", 0) or 0

            results = []
            for entry in scores:
                player_rows = await db.execute_fetchall(
                    "SELECT position, country_code FROM players WHERE id=$1", (entry["player_id"],)
                )
                if not player_rows:
                    continue
                player = dict(player_rows[0])

                # Determine clean sheet
                is_home = player["country_code"] == match_info.get("home_country", "")
                conceded = home_conceded if is_home else away_conceded
                clean_sheet = conceded == 0 and entry.get("minutes_played", 0) >= 60

                total = calculate_points(
                    position=player["position"],
                    minutes=entry.get("minutes_played", 0),
                    goals=entry.get("goals", 0),
                    assists=entry.get("assists", 0),
                    yellow_cards=entry.get("yellow_cards", 0),
                    red_card=entry.get("red_card", False),
                    own_goals=entry.get("own_goals", 0),
                    penalties_missed=entry.get("penalties_missed", 0),
                    penalties_saved=entry.get("penalties_saved", 0),
                    saves=entry.get("saves", 0),
                    goals_conceded=conceded if player["position"] in ("GK", "DEF") else 0,
                    clean_sheet=clean_sheet,
                    rating=entry.get("rating", 0),
                    is_mvp=entry.get("is_mvp", False),
                )

                await db.execute(
                    """INSERT INTO match_scores
                       (player_id, matchday_id, match_id, minutes_played, goals, assists,
                        clean_sheet, yellow_cards, red_card, own_goals, penalties_missed,
                        penalties_saved, saves, goals_conceded, rating, total_points)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                       ON CONFLICT (player_id, matchday_id) DO UPDATE SET
                           match_id=EXCLUDED.match_id,
                           minutes_played=EXCLUDED.minutes_played,
                           goals=EXCLUDED.goals,
                           assists=EXCLUDED.assists,
                           clean_sheet=EXCLUDED.clean_sheet,
                           yellow_cards=EXCLUDED.yellow_cards,
                           red_card=EXCLUDED.red_card,
                           own_goals=EXCLUDED.own_goals,
                           penalties_missed=EXCLUDED.penalties_missed,
                           penalties_saved=EXCLUDED.penalties_saved,
                           saves=EXCLUDED.saves,
                           goals_conceded=EXCLUDED.goals_conceded,
                           rating=EXCLUDED.rating,
                           total_points=EXCLUDED.total_points""",
                    (entry["player_id"], matchday_id, match_id,
                     entry.get("minutes_played", 0), entry.get("goals", 0), entry.get("assists", 0),
                     int(clean_sheet), entry.get("yellow_cards", 0), int(entry.get("red_card", False)),
                     entry.get("own_goals", 0), entry.get("penalties_missed", 0),
                     entry.get("penalties_saved", 0), entry.get("saves", 0),
                     conceded if player["position"] in ("GK", "DEF") else 0,
                     entry.get("rating", 0), total),
                )
                results.append({"player_id": entry["player_id"], "total_points": total})

            await db.commit()
            return results
        finally:
            await db.close()

    @staticmethod
    async def get_team_matchday_points(team_id: str, matchday_id: str) -> int:
        """Calculate a team's points for a matchday, respecting league auto_substitutions setting."""
        db = await get_db()
        try:
            # Get league auto_substitutions setting
            league_row = await db.execute_fetchall(
                """SELECT l.auto_substitutions FROM fantasy_teams ft
                   JOIN leagues l ON ft.league_id = l.id
                   WHERE ft.id=$1""",
                (team_id,),
            )
            auto_subs_enabled = league_row[0]["auto_substitutions"] if league_row else 0

            # Try matchday-specific lineup first, fall back to default
            roster = await db.execute_fetchall(
                """SELECT ml.player_id, ml.is_starter, ml.is_captain, ml.is_vice_captain,
                          p.position
                   FROM matchday_lineups ml JOIN players p ON ml.player_id = p.id
                   WHERE ml.team_id=$1 AND ml.matchday_id=$2""",
                (team_id, matchday_id),
            )
            if not roster:
                # Fall back to default team_players
                roster = await db.execute_fetchall(
                    """SELECT tp.player_id, tp.is_starter, tp.is_captain, tp.is_vice_captain,
                              p.position
                       FROM team_players tp JOIN players p ON tp.player_id = p.id
                       WHERE tp.team_id=$1""",
                    (team_id,),
                )
            starters = [dict(r) for r in roster if r["is_starter"]]
            bench = [dict(r) for r in roster if not r["is_starter"]]

            # Get scores for all team players this matchday
            player_ids = [r["player_id"] for r in roster]
            if not player_ids:
                return 0
            placeholders = ",".join(f"${i+2}" for i in range(len(player_ids)))
            scores = await db.execute_fetchall(
                f"SELECT player_id, total_points, minutes_played FROM match_scores WHERE matchday_id=$1 AND player_id IN ({placeholders})",
                (matchday_id, *player_ids),
            )
            score_map = {dict(s)["player_id"]: dict(s) for s in scores}

            # Auto-substitution (only if enabled in league settings)
            subs_used = 0
            max_subs = 3 if auto_subs_enabled else 0
            active = []
            for s in starters:
                sc = score_map.get(s["player_id"])
                if sc and sc["minutes_played"] > 0:
                    active.append(s)
                elif subs_used < max_subs:
                    # Find bench player of same position
                    sub = None
                    for b in bench:
                        b_score = score_map.get(b["player_id"])
                        if b_score and b_score["minutes_played"] > 0 and b["position"] == s["position"]:
                            sub = b
                            break
                    if not sub:
                        # Try any bench player that played
                        for b in bench:
                            b_score = score_map.get(b["player_id"])
                            if b_score and b_score["minutes_played"] > 0:
                                sub = b
                                break
                    if sub:
                        sub["is_captain"] = s.get("is_captain", 0)
                        sub["is_vice_captain"] = s.get("is_vice_captain", 0)
                        active.append(sub)
                        bench.remove(sub)
                        subs_used += 1
                    else:
                        active.append(s)  # No sub available, keep (0 pts)
                else:
                    active.append(s)  # Max subs reached

            # Calculate total points
            total = 0
            captain_id = None
            vice_captain_id = None
            for p in active:
                if p.get("is_captain"):
                    captain_id = p["player_id"]
                if p.get("is_vice_captain"):
                    vice_captain_id = p["player_id"]

            # Determine who gets captain bonus
            cap_bonus_id = None
            if captain_id and score_map.get(captain_id, {}).get("minutes_played", 0) > 0:
                cap_bonus_id = captain_id
            elif vice_captain_id and score_map.get(vice_captain_id, {}).get("minutes_played", 0) > 0:
                cap_bonus_id = vice_captain_id

            for p in active:
                sc = score_map.get(p["player_id"])
                pts = sc["total_points"] if sc else 0
                if p["player_id"] == cap_bonus_id:
                    pts *= 2  # Captain multiplier
                total += pts

            return total
        finally:
            await db.close()
