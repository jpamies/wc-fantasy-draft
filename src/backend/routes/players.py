from fastapi import APIRouter, HTTPException, Query
from src.backend.config import settings
from src.backend.models import PlayerOut, CountryOut

router = APIRouter(prefix="/api/v1", tags=["players"])

_use_simulator = bool(settings.SIMULATOR_API_URL)


@router.get("/players", response_model=list[PlayerOut])
async def list_players(
    country: str | None = None,
    position: str | None = None,
    search: str | None = None,
    sort: str = "market_value",
    order: str = "desc",
    limit: int = Query(50, le=500),
    offset: int = 0,
):
    if _use_simulator:
        from src.backend.services.simulator_client import fetch_all_squad_players
        all_players = await fetch_all_squad_players()
        rows = all_players
        if country:
            rows = [p for p in rows if p.get("country_code") == country]
        if position:
            rows = [p for p in rows if p.get("position") == position]
        if search:
            term = search.lower()
            rows = [p for p in rows if term in (p.get("name") or "").lower()]
        sort_key = sort if sort in {"market_value", "name", "age", "clause_value", "position"} else "market_value"
        reverse = order.lower() != "asc"
        _default = "" if sort_key in {"name", "position"} else 0
        rows.sort(key=lambda p: p.get(sort_key) if p.get(sort_key) is not None else _default, reverse=reverse)
        rows = rows[offset: offset + limit]
        return [PlayerOut(**r) for r in rows]

    from src.backend.database import get_db
    db = await get_db()
    try:
        where = []
        params: list = []
        if country:
            where.append("country_code=?")
            params.append(country)
        if position:
            where.append("position=?")
            params.append(position)
        if search:
            where.append("name LIKE ?")
            params.append(f"%{search}%")

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        allowed_sorts = {"market_value", "name", "age", "clause_value", "position"}
        sort_col = sort if sort in allowed_sorts else "market_value"
        order_dir = "ASC" if order.lower() == "asc" else "DESC"

        rows = await db.execute_fetchall(
            f"SELECT * FROM players {where_sql} ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?",
            params + [limit, offset],
        )
        return [PlayerOut(**dict(r)) for r in rows]
    finally:
        await db.close()


@router.get("/players/{player_id}", response_model=PlayerOut)
async def get_player(player_id: str):
    if _use_simulator:
        from src.backend.services.simulator_client import fetch_player
        p = await fetch_player(player_id)
        if not p:
            raise HTTPException(404, "Player not found")
        return PlayerOut(**p)

    from src.backend.database import get_db
    db = await get_db()
    try:
        rows = await db.execute_fetchall("SELECT * FROM players WHERE id=?", (player_id,))
        if not rows:
            raise HTTPException(404, "Player not found")
        return PlayerOut(**dict(rows[0]))
    finally:
        await db.close()


@router.get("/countries", response_model=list[CountryOut])
async def list_countries():
    if _use_simulator:
        from src.backend.services.simulator_client import fetch_countries
        return [CountryOut(**c) for c in await fetch_countries()]

    from src.backend.database import get_db
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT c.*, COUNT(p.id) as player_count
               FROM countries c LEFT JOIN players p ON c.code=p.country_code
               GROUP BY c.code ORDER BY c.name"""
        )
        return [CountryOut(**dict(r)) for r in rows]
    finally:
        await db.close()


@router.get("/players/{player_id}/stats")
async def get_player_stats(player_id: str):
    """Get player details + tournament stats from simulator, plus fantasy points."""
    result = {"player": None, "sim_stats": None, "fantasy_scores": []}

    # 1. Player bio from simulator
    if _use_simulator:
        from src.backend.services.simulator_client import get_client
        client = get_client()
        try:
            resp = await client.get(f"/api/v1/players/{player_id}")
            if resp.status_code == 200:
                result["player"] = resp.json()
        except Exception:
            pass

        # 2. Tournament stats from simulator
        try:
            resp = await client.get(f"/api/v1/stats/player/{player_id}")
            if resp.status_code == 200:
                result["sim_stats"] = resp.json()
        except Exception:
            pass

    # 3. Fantasy scoring data from local DB
    from src.backend.database import get_db
    db = await get_db()
    try:
        scores = await db.execute_fetchall(
            """SELECT ms.matchday_id, ms.match_id, ms.minutes_played, ms.goals, ms.assists,
                      ms.yellow_cards, ms.red_card, ms.clean_sheet, ms.saves,
                      ms.goals_conceded, ms.rating, ms.total_points
               FROM match_scores ms WHERE ms.player_id=?
               ORDER BY ms.matchday_id""",
            (player_id,),
        )
        result["fantasy_scores"] = [dict(s) for s in scores]

        # If no player from simulator, try local DB
        if not result["player"]:
            row = await db.execute_fetchall("SELECT * FROM players WHERE id=?", (player_id,))
            if row:
                r = dict(row[0])
                result["player"] = {
                    "id": r["id"], "name": r["name"], "country_code": r["country_code"],
                    "position": r["position"], "club": r.get("club", ""),
                    "photo": r.get("photo", ""), "market_value": r.get("market_value", 0),
                    "age": r.get("age", 0),
                }
    finally:
        await db.close()

    if not result["player"]:
        raise HTTPException(404, "Player not found")
    return result
