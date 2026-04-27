"""Market routes — market windows, clauses, transactions, reposition draft."""
import logging
from fastapi import APIRouter, HTTPException, Depends

from src.backend.auth import get_current_team
from src.backend.models import (
    MarketWindowCreate, MarketWindowUpdate, MarketWindowOut,
    PlayerClausesSetRequest, PlayerClauseOut,
    MarketBudgetOut, AvailablePlayerOut, MarketTransactionOut,
    BuyPlayerRequest,
    RepositionDraftState, RepositionAvailablePlayerOut, RepositionDraftPickRequest,
)
from src.backend.services.market_service import MarketService

router = APIRouter(prefix="/api/v1", tags=["market"])
logger = logging.getLogger(__name__)


# ==================== READ-ONLY MARKET WINDOW INFO ====================

@router.get("/leagues/{league_id}/market-windows")
async def list_market_windows(
    league_id: str,
    current_team: dict = Depends(get_current_team),
):
    """List all market windows in a league."""
    from src.backend.database import get_db
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM market_windows WHERE league_id=? ORDER BY created_at DESC",
            (league_id,),
        )
        return [dict(r) for r in rows]
    finally:
        await db.close()


@router.get("/leagues/{league_id}/market/{window_id}")
async def get_market_window_detail(
    league_id: str,
    window_id: int,
    current_team: dict = Depends(get_current_team),
):
    """Get details of a specific market window."""
    window = await MarketService.get_market_window(window_id)
    if not window or window.get("league_id") != league_id:
        raise HTTPException(404, "Market window not found")
    return window


# ==================== MARKET WINDOWS (COMMISSIONER) ====================

@router.post("/leagues/{league_id}/admin/market-windows")
async def create_market_window(
    league_id: str,
    body: MarketWindowCreate,
    current_team: dict = Depends(get_current_team),
):
    """Create a new market window (commissioner only)."""
    if not current_team["is_commissioner"]:
        raise HTTPException(403, "Only commissioner can create market windows")

    try:
        result = await MarketService.create_market_window(
            league_id=league_id,
            phase=body.phase,
            market_type=body.market_type,
            clause_window_start=body.clause_window_start,
            clause_window_end=body.clause_window_end,
            market_window_start=body.market_window_start,
            market_window_end=body.market_window_end,
            reposition_draft_start=body.reposition_draft_start,
            reposition_draft_end=body.reposition_draft_end,
            max_buys=body.max_buys,
            max_sells=body.max_sells,
            initial_budget=body.initial_budget,
            protect_budget=body.protect_budget,
        )
        return result
    except Exception as e:
        logger.error(f"Error creating market window: {e}")
        raise HTTPException(500, str(e))


@router.patch("/leagues/{league_id}/admin/market-windows/{window_id}")
async def update_market_window(
    league_id: str,
    window_id: int,
    body: MarketWindowUpdate,
    current_team: dict = Depends(get_current_team),
):
    """Update market window configuration (commissioner only)."""
    if not current_team["is_commissioner"]:
        raise HTTPException(403, "Only commissioner can update market windows")

    try:
        updates = body.dict(exclude_none=True)
        result = await MarketService.update_market_window(window_id, updates)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Error updating market window: {e}")
        raise HTTPException(500, str(e))


@router.post("/leagues/{league_id}/admin/market-windows/{window_id}/start-clause-phase")
async def start_clause_phase(
    league_id: str,
    window_id: int,
    current_team: dict = Depends(get_current_team),
):
    """Start clause window phase (commissioner only)."""
    if not current_team["is_commissioner"]:
        raise HTTPException(403, "Only commissioner can start phases")

    try:
        result = await MarketService.start_clause_phase(window_id)
        return result
    except Exception as e:
        logger.error(f"Error starting clause phase: {e}")
        raise HTTPException(500, str(e))


@router.post("/leagues/{league_id}/admin/market-tick")
async def market_tick(
    league_id: str,
    current_team: dict = Depends(get_current_team),
):
    """Force-evaluate market window deadlines and run any due transitions now.

    Useful when the watchdog hasn't run yet or to bypass timezone confusion.
    Only transitions whose deadline has actually passed are applied.
    """
    if current_team.get("league_id") != league_id or not current_team.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")

    from datetime import datetime, timezone, timedelta
    from src.backend.database import get_db
    from src.backend.main import _parse_iso

    transitions = 0
    db = await get_db()
    try:
        windows = await db.execute_fetchall(
            "SELECT * FROM market_windows WHERE league_id=? AND status != 'completed'",
            (league_id,),
        )
    finally:
        await db.close()

    now_dt = datetime.now(timezone.utc)
    far_future = now_dt + timedelta(days=365)
    for w in windows:
        wid = w["id"]
        s = w["status"]
        try:
            if s == "scheduled" and (_parse_iso(w["clause_window_start"]) or far_future) <= now_dt:
                await MarketService.start_clause_phase(wid); transitions += 1
                s = "clause_window"
            if s == "clause_window" and (_parse_iso(w["clause_window_end"]) or far_future) <= now_dt:
                await MarketService.start_market_phase(wid); transitions += 1
                s = "market_open"
            if s == "market_open" and (_parse_iso(w["market_window_end"]) or far_future) <= now_dt:
                await MarketService.close_market(wid); transitions += 1
                s = "market_closed"
            if s == "market_closed" and (_parse_iso(w["reposition_draft_start"]) or far_future) <= now_dt:
                await MarketService.start_reposition_draft(wid); transitions += 1
        except Exception as e:
            logger.error(f"market-tick error on window {wid}: {e}")

    return {"ok": True, "transitions": transitions, "now_utc": now_dt.isoformat()}


@router.post("/leagues/{league_id}/admin/market-windows/{window_id}/start-market-phase")
async def start_market_phase(
    league_id: str,
    window_id: int,
    current_team: dict = Depends(get_current_team),
):
    """Transition from clause_window to market_open (commissioner only)."""
    if not current_team["is_commissioner"]:
        raise HTTPException(403, "Only commissioner can start phases")

    try:
        result = await MarketService.start_market_phase(window_id)
        return result
    except Exception as e:
        logger.error(f"Error starting market phase: {e}")
        raise HTTPException(500, str(e))


@router.post("/leagues/{league_id}/admin/market-windows/{window_id}/close-market")
async def close_market(
    league_id: str,
    window_id: int,
    current_team: dict = Depends(get_current_team),
):
    """Close market window (commissioner only)."""
    if not current_team["is_commissioner"]:
        raise HTTPException(403, "Only commissioner can close market")

    try:
        result = await MarketService.close_market(window_id)
        return result
    except Exception as e:
        logger.error(f"Error closing market: {e}")
        raise HTTPException(500, str(e))


@router.post("/leagues/{league_id}/admin/market-windows/{window_id}/start-reposition-draft")
async def start_reposition_draft(
    league_id: str,
    window_id: int,
    current_team: dict = Depends(get_current_team),
):
    """Start reposition draft phase (commissioner only)."""
    if not current_team["is_commissioner"]:
        raise HTTPException(403, "Only commissioner can start reposition draft")

    try:
        result = await MarketService.start_reposition_draft(window_id)
        return result
    except Exception as e:
        logger.error(f"Error starting reposition draft: {e}")
        raise HTTPException(500, str(e))


# ==================== PLAYER CLAUSES ====================

@router.get("/teams/{team_id}/market/{window_id}/clauses")
async def get_team_clauses(
    team_id: str,
    window_id: int,
    current_team: dict = Depends(get_current_team),
):
    """Get clauses set by current team."""
    if current_team["team_id"] != team_id:
        raise HTTPException(403, "Can only view own clauses")

    try:
        clauses = await MarketService.get_team_clauses(window_id, team_id)
        return clauses
    except Exception as e:
        logger.error(f"Error getting clauses: {e}")
        raise HTTPException(500, str(e))


@router.post("/teams/{team_id}/market/{window_id}/clauses/set")
async def set_player_clauses(
    team_id: str,
    window_id: int,
    body: PlayerClausesSetRequest,
    current_team: dict = Depends(get_current_team),
):
    """Set clause protection for players."""
    if current_team["team_id"] != team_id:
        raise HTTPException(403, "Can only set own clauses")

    try:
        result = await MarketService.set_player_clauses(
            window_id=window_id,
            team_id=team_id,
            clauses=[c.dict() for c in body.clauses],
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error(f"Error setting clauses: {e}")
        raise HTTPException(500, str(e))


# ==================== MARKET TRANSACTIONS ====================

@router.get("/leagues/{league_id}/market/{window_id}/available-players")
async def get_available_players(
    league_id: str,
    window_id: int,
    position: str = None,
    current_team: dict = Depends(get_current_team),
):
    """Get list of players available for purchase."""
    try:
        players = await MarketService.get_available_players(
            league_id=league_id,
            window_id=window_id,
            position=position,
        )
        return players
    except Exception as e:
        logger.error(f"Error getting available players: {e}")
        raise HTTPException(500, str(e))


@router.get("/teams/{team_id}/market/{window_id}/budget", response_model=MarketBudgetOut)
async def get_market_budget(
    team_id: str,
    window_id: int,
    current_team: dict = Depends(get_current_team),
):
    """Get current budget for team in market window."""
    if current_team["team_id"] != team_id:
        raise HTTPException(403, "Can only view own budget")

    try:
        budget = await MarketService.get_market_budget(window_id, team_id)
        if not budget:
            # Budget not yet initialized (still in clause_window phase)
            window = await MarketService.get_market_window(window_id)
            if not window:
                raise HTTPException(404, "Market window not found")
            return MarketBudgetOut(
                initial_budget=window["initial_budget"],
                earned_from_sales=0,
                spent_on_buys=0,
                remaining_budget=window["initial_budget"],
                buys_count=0,
                sells_count=0,
                max_buys=window["max_buys"],
                max_sells=window["max_sells"],
            )
        return budget
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting budget: {e}")
        raise HTTPException(500, str(e))


@router.post("/teams/{team_id}/market/{window_id}/buy-player")
async def buy_player(
    team_id: str,
    window_id: int,
    body: BuyPlayerRequest,
    current_team: dict = Depends(get_current_team),
):
    """Execute player purchase transaction."""
    if current_team["team_id"] != team_id:
        raise HTTPException(403, "Can only buy for own team")

    try:
        result = await MarketService.buy_player(
            window_id=window_id,
            buyer_team_id=team_id,
            player_id=body.player_id,
        )
        if not result.get("success"):
            raise HTTPException(400, result.get("reason", "Transaction failed"))
        return result
    except Exception as e:
        logger.error(f"Error buying player: {e}")
        raise HTTPException(500, str(e))


@router.get("/teams/{team_id}/market/{window_id}/transaction-history")
async def get_transaction_history(
    team_id: str,
    window_id: int,
    current_team: dict = Depends(get_current_team),
):
    """Get transaction history for team."""
    if current_team["team_id"] != team_id:
        raise HTTPException(403, "Can only view own transaction history")

    try:
        transactions = await MarketService.get_transaction_history(window_id, team_id)
        return transactions
    except Exception as e:
        logger.error(f"Error getting transaction history: {e}")
        raise HTTPException(500, str(e))


# ==================== REPOSITION DRAFT ====================

@router.get("/leagues/{league_id}/market/{window_id}/reposition-draft-state", response_model=RepositionDraftState)
async def get_reposition_draft_state(
    league_id: str,
    window_id: int,
    current_team: dict = Depends(get_current_team),
):
    """Get current state of reposition draft."""
    try:
        state = await MarketService.get_reposition_draft_state(window_id, current_team["team_id"])
        return state
    except Exception as e:
        logger.error(f"Error getting reposition draft state: {e}")
        raise HTTPException(500, str(e))


@router.get("/leagues/{league_id}/market/{window_id}/reposition-available-players")
async def get_reposition_available_players(
    league_id: str,
    window_id: int,
    current_team: dict = Depends(get_current_team),
):
    """Get players available for reposition draft."""
    try:
        players = await MarketService.get_reposition_available_players(
            league_id=league_id,
            window_id=window_id,
        )
        return players
    except Exception as e:
        logger.error(f"Error getting available players: {e}")
        raise HTTPException(500, str(e))


@router.post("/teams/{team_id}/market/{window_id}/reposition-draft-pick")
async def make_reposition_draft_pick(
    team_id: str,
    window_id: int,
    body: RepositionDraftPickRequest,
    current_team: dict = Depends(get_current_team),
):
    """Make a pick in reposition draft."""
    if current_team["team_id"] != team_id:
        raise HTTPException(403, "Can only make picks for own team")

    try:
        result = await MarketService.make_reposition_draft_pick(
            window_id=window_id,
            team_id=team_id,
            player_id=body.player_id,
        )
        if not result.get("success"):
            raise HTTPException(400, result.get("reason", "Pick failed"))
        return result
    except Exception as e:
        logger.error(f"Error making draft pick: {e}")
        raise HTTPException(500, str(e))

