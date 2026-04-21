"""Import player data from data/transfermarkt/*.json into SQLite."""
import asyncio
import json
import os

from src.backend.database import get_db, init_db
from src.backend.config import settings


async def import_data():
    await init_db()
    db = await get_db()
    try:
        data_dir = settings.TRANSFERMARKT_DATA_DIR
        if not os.path.isdir(data_dir):
            print(f"Data directory not found: {data_dir}")
            return

        # Clear existing player/country data for idempotent reimport
        await db.execute("DELETE FROM draft_picks")
        await db.execute("DELETE FROM team_players")
        await db.execute("DELETE FROM match_scores")
        await db.execute("DELETE FROM players")
        await db.execute("DELETE FROM countries")

        total_players = 0
        files = sorted(f for f in os.listdir(data_dir) if f.endswith(".json"))

        for filename in files:
            filepath = os.path.join(data_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            country = data["country"]
            code = country["code"]

            await db.execute(
                "INSERT OR REPLACE INTO countries (code, name, name_local, flag, confederation) VALUES (?,?,?,?,?)",
                (code, country["name"], country.get("nameLocal", ""), country.get("flag", ""), country.get("confederation", "")),
            )

            for player in data["players"]:
                player_id = f"{code}-{player['id']:03d}"
                market_value = player.get("marketValue", 0) or 0
                clause_value = int(market_value * 1.5)

                await db.execute(
                    """INSERT OR REPLACE INTO players
                    (id, name, country_code, position, detailed_position, club, club_logo, age, market_value, photo, clause_value)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        player_id,
                        player["name"],
                        code,
                        player["position"],
                        player.get("detailedPosition", ""),
                        player.get("club", ""),
                        player.get("clubLogo", ""),
                        player.get("age", 0),
                        market_value,
                        player.get("photo", ""),
                        clause_value,
                    ),
                )
                total_players += 1

            print(f"  {code}: {len(data['players'])} players")

        await db.commit()
        print(f"\nImported {total_players} players from {len(files)} countries")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(import_data())
