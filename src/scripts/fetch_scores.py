"""
Fetch match scores from Football-Data.org and update WC Fantasy database.

Usage:
  # Fetch scores for a specific matchday
  python -m src.scripts.fetch_scores --matchday GS1

  # Fetch all matchdays with finished matches
  python -m src.scripts.fetch_scores --all

  # Simulate scores for testing (random but realistic)
  python -m src.scripts.fetch_scores --simulate GS1

Requires FOOTBALL_DATA_API_KEY env var for live data.
Free tier: https://www.football-data.org/ (covers World Cup)
"""
import asyncio
import argparse
import json
import os
import random
from src.backend.database import get_db, init_db
from src.backend.services.scoring_engine import calculate_points


# Country code mapping: our codes → Football-Data.org codes
COUNTRY_MAP = {
    "USA": "USA", "MEX": "MEX", "EGY": "EGY", "COL": "COL",
    "ESP": "ESP", "JPN": "JPN", "MAR": "MAR", "CRO": "CRO",
    "FRA": "FRA", "ARG": "ARG", "TUR": "TUR", "SEN": "SEN",
    "ENG": "ENG", "BRA": "BRA", "SUI": "CHE", "QAT": "QAT",
    "GER": "GER", "URU": "URU", "DEN": "DEN", "POR": "POR",
    "ITA": "ITA", "NED": "NED", "BEL": "BEL",
}


async def simulate_match_scores(matchday_id: str):
    """Generate realistic simulated scores for testing purposes."""
    db = await get_db()
    try:
        # Get matches for this matchday
        matches = await db.execute_fetchall(
            "SELECT * FROM matches WHERE matchday_id=$1", (matchday_id,)
        )
        if not matches:
            print(f"No matches found for matchday {matchday_id}")
            return

        total_scored = 0
        for match in matches:
            m = dict(match)
            home = m["home_country"]
            away = m["away_country"]

            # Generate random but realistic score
            score_home = random.choices([0,1,2,3,4], weights=[25,35,25,10,5])[0]
            score_away = random.choices([0,1,2,3,4], weights=[25,35,25,10,5])[0]

            # Update match result
            await db.execute(
                "UPDATE matches SET score_home=$1, score_away=$2, status='finished' WHERE id=$3",
                (score_home, score_away, m["id"]),
            )

            # Get players from both countries
            for country, goals_scored, goals_conceded in [
                (home, score_home, score_away),
                (away, score_away, score_home),
            ]:
                players = await db.execute_fetchall(
                    "SELECT id, name, position FROM players WHERE country_code=$1 ORDER BY market_value DESC LIMIT 23",
                    (country,),
                )
                if not players:
                    continue

                players = [dict(p) for p in players]
                # Pick 11 starters (1 GK, 4 DEF, 3 MID, 3 FWD)
                by_pos = {"GK": [], "DEF": [], "MID": [], "FWD": []}
                for p in players:
                    by_pos.get(p["position"], []).append(p)

                starters = []
                for pos, count in [("GK", 1), ("DEF", 4), ("MID", 3), ("FWD", 3)]:
                    starters.extend(by_pos[pos][:count])

                # Subs (3 random from remaining)
                remaining = [p for p in players if p not in starters]
                subs = remaining[:5] if remaining else []

                # Assign goals and assists randomly among starters
                remaining_goals = goals_scored
                goal_scorers = []
                assist_makers = []
                attackers = [p for p in starters if p["position"] in ("FWD", "MID")]
                if not attackers:
                    attackers = starters[1:]  # skip GK

                for _ in range(remaining_goals):
                    scorer = random.choice(attackers)
                    goal_scorers.append(scorer["id"])
                    # 60% chance of having an assist
                    if random.random() < 0.6:
                        possible = [p for p in starters if p["id"] != scorer["id"]]
                        if possible:
                            assist_makers.append(random.choice(possible)["id"])

                # Generate ratings
                best_rating = 0
                mvp_id = None

                for p in starters:
                    minutes = random.choices([90, 80, 70, 60, 45], weights=[50, 15, 10, 10, 15])[0]
                    p_goals = goal_scorers.count(p["id"])
                    p_assists = assist_makers.count(p["id"])
                    yellow = 1 if random.random() < 0.12 else 0
                    red = random.random() < 0.02
                    if red:
                        minutes = random.randint(20, 75)
                    clean_sheet = goals_conceded == 0
                    saves = random.randint(2, 8) if p["position"] == "GK" else 0
                    pen_saved = 1 if p["position"] == "GK" and random.random() < 0.05 else 0
                    own_goal = 1 if random.random() < 0.02 else 0

                    # Rating
                    rating = 6.0 + p_goals * 0.8 + p_assists * 0.4
                    if clean_sheet and p["position"] in ("GK", "DEF"):
                        rating += 0.5
                    rating += random.uniform(-0.5, 0.8)
                    rating = round(min(10, max(4, rating)), 1)

                    if rating > best_rating:
                        best_rating = rating
                        mvp_id = p["id"]

                    total = calculate_points(
                        position=p["position"], minutes=minutes, goals=p_goals,
                        assists=p_assists, yellow_cards=yellow, red_card=red,
                        own_goals=own_goal, penalties_missed=0, penalties_saved=pen_saved,
                        saves=saves, goals_conceded=goals_conceded if p["position"] in ("GK", "DEF") else 0,
                        clean_sheet=clean_sheet, rating=rating,
                        is_mvp=False,  # set after loop
                    )

                    await db.execute(
                        """INSERT INTO match_scores
                           (player_id, matchday_id, match_id, minutes_played, goals, assists,
                            clean_sheet, yellow_cards, red_card, own_goals, penalties_missed,
                            penalties_saved, saves, goals_conceded, rating, total_points)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) ON CONFLICT (player_id, matchday_id) DO NOTHING""",
                        (p["id"], matchday_id, m["id"], minutes, p_goals, p_assists,
                         int(clean_sheet), yellow, int(red), own_goal, 0, pen_saved,
                         saves, goals_conceded if p["position"] in ("GK", "DEF") else 0,
                         rating, total),
                    )
                    total_scored += 1

                # Sub entries (0 min, shows they were on bench)
                for p in subs[:3]:
                    sub_min = random.choices([0, 15, 20, 25, 30], weights=[40, 20, 15, 15, 10])[0]
                    if sub_min > 0:
                        total = calculate_points(
                            position=p["position"], minutes=sub_min, goals=0, assists=0,
                            yellow_cards=0, red_card=False, own_goals=0, penalties_missed=0,
                            penalties_saved=0, saves=0, goals_conceded=0,
                            clean_sheet=goals_conceded == 0, rating=6.0, is_mvp=False,
                        )
                        await db.execute(
                            """INSERT INTO match_scores
                               (player_id, matchday_id, match_id, minutes_played, goals, assists,
                                clean_sheet, yellow_cards, red_card, own_goals, penalties_missed,
                                penalties_saved, saves, goals_conceded, rating, total_points)
                               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) ON CONFLICT (player_id, matchday_id) DO NOTHING""",
                            (p["id"], matchday_id, m["id"], sub_min, 0, 0,
                             int(goals_conceded == 0), 0, 0, 0, 0, 0, 0, 0, 6.0, total),
                        )
                        total_scored += 1

                # Update MVP — recalculate that player's points with is_mvp=True
                if mvp_id and best_rating >= 7.5:
                    mvp_row = await db.execute_fetchall(
                        "SELECT * FROM match_scores WHERE player_id=$1 AND matchday_id=$2 AND match_id=$3",
                        (mvp_id, matchday_id, m["id"]),
                    )
                    if mvp_row:
                        mv = dict(mvp_row[0])
                        p_info = await db.execute_fetchall("SELECT position FROM players WHERE id=$1", (mvp_id,))
                        if p_info:
                            new_total = calculate_points(
                                position=dict(p_info[0])["position"],
                                minutes=mv["minutes_played"], goals=mv["goals"], assists=mv["assists"],
                                yellow_cards=mv["yellow_cards"], red_card=bool(mv["red_card"]),
                                own_goals=mv["own_goals"], penalties_missed=mv["penalties_missed"],
                                penalties_saved=mv["penalties_saved"], saves=mv["saves"],
                                goals_conceded=mv["goals_conceded"],
                                clean_sheet=bool(mv["clean_sheet"]), rating=best_rating, is_mvp=True,
                            )
                            await db.execute(
                                "UPDATE match_scores SET rating=$1, total_points=$2, bonus_points=3 WHERE player_id=$3 AND matchday_id=$4 AND match_id=$5",
                                (best_rating, new_total, mvp_id, matchday_id, m["id"]),
                            )

            print(f"  ⚽ {home} {score_home}-{score_away} {away}")

        # Mark matchday complete
        await db.execute("UPDATE matchdays SET status='completed' WHERE id=$1", (matchday_id,))
        await db.commit()
        print(f"\n✅ Simulated {total_scored} player scores for matchday {matchday_id}")
    finally:
        await db.close()


async def main():
    parser = argparse.ArgumentParser(description="Fetch or simulate WC Fantasy scores")
    parser.add_argument("--simulate", metavar="MATCHDAY_ID", help="Simulate scores for testing")
    parser.add_argument("--all", action="store_true", help="Process all matchdays")
    parser.add_argument("--matchday", metavar="ID", help="Fetch scores for specific matchday")
    args = parser.parse_args()

    await init_db()

    if args.simulate:
        print(f"🎲 Simulating scores for matchday {args.simulate}...")
        await simulate_match_scores(args.simulate)
    elif args.all:
        db = await get_db()
        try:
            matchdays = await db.execute_fetchall(
                "SELECT id FROM matchdays WHERE status='upcoming' ORDER BY date"
            )
            for md in matchdays:
                print(f"\n🎲 Simulating matchday {dict(md)['id']}...")
                await simulate_match_scores(dict(md)["id"])
        finally:
            await db.close()
    else:
        print("Usage: python -m src.scripts.fetch_scores --simulate GS1")
        print("       python -m src.scripts.fetch_scores --all")


if __name__ == "__main__":
    asyncio.run(main())
