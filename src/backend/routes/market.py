from fastapi import APIRouter, HTTPException, Depends
from src.backend.auth import get_current_team
from src.backend.database import get_db
from src.backend.services.market_engine import MarketEngine
from src.backend.models import ClauseRequest, OfferCreate, OfferRespond, BidRequest, ReleaseRequest, TransferOut

router = APIRouter(prefix="/api/v1", tags=["market"])


@router.get("/leagues/{league_id}/market")
async def get_market(league_id: str):
    db = await get_db()
    try:
        lg = await db.execute_fetchall("SELECT transfer_window_open FROM leagues WHERE id=?", (league_id,))
        if not lg:
            raise HTTPException(404, "League not found")
        window_open = bool(lg[0]["transfer_window_open"])

        free_agents = await MarketEngine.get_free_agents(league_id)

        pending = await db.execute_fetchall(
            """SELECT t.*, p.name as player_name FROM transfers t
               JOIN players p ON t.player_id=p.id
               WHERE t.league_id=? AND t.status='pending' ORDER BY t.created_at DESC""",
            (league_id,),
        )
        recent = await db.execute_fetchall(
            """SELECT t.*, p.name as player_name FROM transfers t
               JOIN players p ON t.player_id=p.id
               WHERE t.league_id=? AND t.status='completed' ORDER BY t.resolved_at DESC LIMIT 20""",
            (league_id,),
        )
        return {
            "window_open": window_open,
            "free_agents": free_agents,
            "pending_offers": [dict(r) for r in pending],
            "recent_transfers": [dict(r) for r in recent],
        }
    finally:
        await db.close()


@router.post("/leagues/{league_id}/market/clause")
async def execute_clause(league_id: str, body: ClauseRequest, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    result = await MarketEngine.execute_clause(league_id, auth["team_id"], body.player_id)
    if "error" in result:
        code = 402 if "budget" in result["error"].lower() else 400
        raise HTTPException(code, result["error"])
    return result


@router.post("/leagues/{league_id}/market/offer")
async def create_offer(league_id: str, body: OfferCreate, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    result = await MarketEngine.create_offer(
        league_id, auth["team_id"], body.to_team_id,
        body.players_offered, body.players_requested, body.amount,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/leagues/{league_id}/market/offer/{offer_id}/respond")
async def respond_offer(league_id: str, offer_id: str, body: OfferRespond, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    result = await MarketEngine.respond_offer(offer_id, auth["team_id"], body.action)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/leagues/{league_id}/market/bid")
async def bid_free_agent(league_id: str, body: BidRequest, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    result = await MarketEngine.bid_free_agent(league_id, auth["team_id"], body.player_id, body.amount)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/leagues/{league_id}/market/release")
async def release_player(league_id: str, body: ReleaseRequest, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    result = await MarketEngine.release_player(league_id, auth["team_id"], body.player_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/leagues/{league_id}/admin/open-window")
async def open_window(league_id: str, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id or not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    db = await get_db()
    try:
        await db.execute("UPDATE leagues SET transfer_window_open=1 WHERE id=?", (league_id,))
        await db.commit()
        return {"ok": True, "window_open": True}
    finally:
        await db.close()


@router.post("/leagues/{league_id}/admin/close-window")
async def close_window(league_id: str, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id or not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    resolved = await MarketEngine.resolve_bids(league_id)
    db = await get_db()
    try:
        await db.execute("UPDATE leagues SET transfer_window_open=0 WHERE id=?", (league_id,))
        await db.commit()
        return {"ok": True, "window_open": False, "bids_resolved": len(resolved)}
    finally:
        await db.close()
