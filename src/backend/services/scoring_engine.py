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
            match_row = await db.execute_fetchall("SELECT * FROM matches WHERE id=?", (match_id,))
            match_info = dict(match_row[0]) if match_row else {}

            home_conceded = match_info.get("score_away", 0) or 0
            away_conceded = match_info.get("score_home", 0) or 0

            results = []
            for entry in scores:
                player_rows = await db.execute_fetchall(
                    "SELECT position, country_code FROM players WHERE id=?", (entry["player_id"],)
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
                    """INSERT OR REPLACE INTO match_scores
                       (player_id, matchday_id, match_id, minutes_played, goals, assists,
                        clean_sheet, yellow_cards, red_card, own_goals, penalties_missed,
                        penalties_saved, saves, goals_conceded, rating, total_points)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
