"""HTTP client for wc-simulator API — fetches player data live."""
import httpx
from src.backend.config import settings

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.SIMULATOR_API_URL.rstrip("/"),
            timeout=10.0,
        )
    return _client


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


def _to_fantasy_player(p: dict) -> dict:
    """Map simulator PlayerOut fields to fantasy PlayerOut fields."""
    mv = p.get("market_value", 0) or 0
    return {
        "id": p["id"],
        "name": p["name"],
        "country_code": p["country_code"],
        "position": p["position"],
        "detailed_position": p.get("detailed_position") or "",
        "club": p.get("club") or "",
        "club_logo": p.get("club_logo") or "",
        "age": p.get("age") or 0,
        "market_value": mv,
        "photo": p.get("photo") or "",
        "clause_value": int(mv * 1.5),
        "strength": p.get("strength", 50),
    }


async def fetch_players(
    *,
    country: str | None = None,
    position: str | None = None,
    search: str | None = None,
    sort: str = "market_value",
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Fetch players from wc-simulator, mapped to fantasy format."""
    params: dict = {"limit": limit, "offset": offset, "sort": sort}
    if country:
        params["country"] = country
    if position:
        params["position"] = position
    if search:
        params["search"] = search

    client = get_client()
    resp = await client.get("/api/v1/players", params=params)
    resp.raise_for_status()
    return [_to_fantasy_player(p) for p in resp.json()]


async def fetch_player(player_id: str) -> dict | None:
    """Fetch a single player from wc-simulator."""
    client = get_client()
    resp = await client.get(f"/api/v1/players/{player_id}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return _to_fantasy_player(resp.json())


async def fetch_countries() -> list[dict]:
    """Fetch countries list from wc-simulator."""
    client = get_client()
    resp = await client.get("/api/v1/countries")
    resp.raise_for_status()
    return resp.json()


async def fetch_calendar() -> list[dict]:
    """Fetch full calendar (matchdays + matches) from wc-simulator."""
    client = get_client()
    resp = await client.get("/api/v1/tournament/calendar", timeout=15.0)
    resp.raise_for_status()
    return resp.json()


async def fetch_tournament_overview() -> dict:
    """Fetch tournament overview (current_phase, matches_played, etc.)."""
    client = get_client()
    resp = await client.get("/api/v1/tournament/overview", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


async def fetch_standings() -> dict[str, list[dict]]:
    """Fetch group standings from wc-simulator.
    Returns {group_letter: [team_dicts sorted by position]}."""
    client = get_client()
    resp = await client.get("/api/v1/tournament/standings", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


async def fetch_squad_players(country_code: str) -> list[dict]:
    """Fetch squad-selected players for a country."""
    client = get_client()
    resp = await client.get(f"/api/v1/squads/{country_code}")
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return [_to_fantasy_player(p) for p in resp.json()]


async def fetch_all_squad_players() -> list[dict]:
    """Fetch all squad-selected players for all 48 countries in one call."""
    client = get_client()
    resp = await client.get("/api/v1/squads/all-players", timeout=30.0)
    resp.raise_for_status()
    return [_to_fantasy_player(p) for p in resp.json()]


async def ensure_player_in_db(player_id: str) -> dict | None:
    """Fetch player from simulator and upsert into local DB for FK integrity.
    Returns the player dict or None if not found."""
    player = await fetch_player(player_id)
    if not player:
        return None

    from src.backend.database import get_db
    db = await get_db()
    try:
        # Ensure country exists
        await db.execute(
            "INSERT INTO countries (code, name) VALUES ($1, $2) ON CONFLICT (code) DO NOTHING",
            (player["country_code"], player["country_code"]),
        )
        await db.execute(
            """INSERT INTO players
               (id, name, country_code, position, detailed_position, club, club_logo, age, market_value, photo, clause_value)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
               ON CONFLICT (id) DO UPDATE SET
                   name=EXCLUDED.name,
                   country_code=EXCLUDED.country_code,
                   position=EXCLUDED.position,
                   detailed_position=EXCLUDED.detailed_position,
                   club=EXCLUDED.club,
                   club_logo=EXCLUDED.club_logo,
                   age=EXCLUDED.age,
                   market_value=EXCLUDED.market_value,
                   photo=EXCLUDED.photo,
                   clause_value=EXCLUDED.clause_value""",
            (
                player["id"], player["name"], player["country_code"],
                player["position"], player["detailed_position"],
                player["club"], player["club_logo"], player["age"],
                player["market_value"], player["photo"], player["clause_value"],
            ),
        )
        await db.commit()
        return player
    finally:
        await db.close()


async def ensure_team_players_in_db(team_id: str):
    """Ensure all players owned by a team exist in the local players table
    with full data. Re-fetches stubs (photo missing) created by score sync."""
    from src.backend.database import get_db
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT tp.player_id FROM team_players tp
               LEFT JOIN players p ON tp.player_id = p.id
               WHERE tp.team_id = $1
                 AND (p.id IS NULL OR COALESCE(p.photo, '') = '')""",
            (team_id,),
        )
        missing_ids = [r["player_id"] for r in rows]
    finally:
        await db.close()

    for pid in missing_ids:
        try:
            await ensure_player_in_db(pid)
        except Exception:
            pass
