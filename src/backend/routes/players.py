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
        from src.backend.services.simulator_client import fetch_players
        rows = await fetch_players(
            country=country, position=position, search=search,
            sort=sort, limit=limit, offset=offset,
        )
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
