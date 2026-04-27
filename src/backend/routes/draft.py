import json
from fastapi import APIRouter, HTTPException, Depends, WebSocket, WebSocketDisconnect
from src.backend.auth import get_current_team
from src.backend.services.draft_engine import DraftEngine
from src.backend.models import DraftPickRequest, DraftState

router = APIRouter(prefix="/api/v1", tags=["draft"])

# Active WebSocket connections per league
_draft_connections: dict[str, list[WebSocket]] = {}


async def _broadcast(league_id: str, message: dict):
    conns = _draft_connections.get(league_id, [])
    dead = []
    for ws in conns:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        conns.remove(ws)


@router.post("/leagues/{league_id}/draft/start")
async def start_draft(league_id: str, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id or not auth.get("is_commissioner"):
        raise HTTPException(403, "Commissioner only")
    result = await DraftEngine.start_draft(league_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    
    # Enable autodraft for all bots
    from src.backend.services.bot_service import enable_autodraft_for_bots
    await enable_autodraft_for_bots(league_id)
    
    state = await DraftEngine.get_draft_state(league_id)
    await _broadcast(league_id, {"type": "draft_started", "state": state})
    
    # Process autodraft immediately (bots will pick if it's their turn)
    await _process_and_broadcast_autodraft(league_id)
    
    return result


@router.get("/leagues/{league_id}/draft")
async def get_draft(league_id: str):
    state = await DraftEngine.get_draft_state(league_id)
    if not state:
        raise HTTPException(404, "No draft found")
    return state


@router.get("/leagues/{league_id}/draft/available")
async def get_available(league_id: str, position: str | None = None, search: str | None = None, country: str | None = None):
    return await DraftEngine.get_available_players(league_id, position, search, country)


@router.post("/leagues/{league_id}/draft/pick")
async def make_pick(league_id: str, body: DraftPickRequest, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    result = await DraftEngine.make_pick(league_id, auth["team_id"], body.player_id)
    if "error" in result:
        raise HTTPException(400, result["error"])

    # Broadcast pick
    state = await DraftEngine.get_draft_state(league_id)
    await _broadcast(league_id, {
        "type": "pick" if state and state["status"] == "in_progress" else "draft_end",
        "pick": result,
        "state": state,
    })

    # Process any autodraft teams that are next in line
    await _process_and_broadcast_autodraft(league_id)

    return result


@router.post("/leagues/{league_id}/draft/autopick")
async def auto_pick(league_id: str, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    result = await DraftEngine.auto_pick(league_id, auth["team_id"])
    if "error" in result:
        raise HTTPException(400, result["error"])
    state = await DraftEngine.get_draft_state(league_id)
    await _broadcast(league_id, {"type": "pick", "pick": result, "state": state})

    # Process any autodraft teams that are next in line
    await _process_and_broadcast_autodraft(league_id)

    return result


@router.post("/leagues/{league_id}/draft/autodraft")
async def toggle_autodraft(league_id: str, auth: dict = Depends(get_current_team)):
    """Enable autodraft for the current team. The system will automatically
    pick the best available player when it's this team's turn, ensuring
    a balanced squad (2-3 GK, 5+ DEF, 5+ MID, 5+ FWD)."""
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    team_id = auth["team_id"]
    currently_enabled = await DraftEngine.is_autodraft(league_id, team_id)
    await DraftEngine.set_autodraft(league_id, team_id, not currently_enabled)
    new_state = not currently_enabled

    # If just enabled and it's currently this team's turn, trigger immediately
    if new_state:
        await _process_and_broadcast_autodraft(league_id)

    return {"ok": True, "autodraft": new_state, "team_id": team_id}


@router.get("/leagues/{league_id}/draft/autodraft")
async def get_autodraft_status(league_id: str, auth: dict = Depends(get_current_team)):
    """Get autodraft status and queue for this team."""
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    return {
        "team_autodraft": await DraftEngine.is_autodraft(league_id, auth["team_id"]),
        "queue": await DraftEngine.get_queue(league_id, auth["team_id"]),
        "all": await DraftEngine.get_autodraft_teams(league_id),
    }


# --- Draft Queue (Cola de Draft) ---

@router.get("/leagues/{league_id}/draft/queue")
async def get_queue(league_id: str, auth: dict = Depends(get_current_team)):
    """Get this team's draft queue with player details."""
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    queue_ids = await DraftEngine.get_queue(league_id, auth["team_id"])
    if not queue_ids:
        return []

    from src.backend.config import settings

    if settings.SIMULATOR_API_URL:
        # Fetch player details from simulator
        from src.backend.services.simulator_client import fetch_player
        from src.backend.database import get_db
        db = await get_db()
        try:
            drafts = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=?", (league_id,))
            picked_set = set()
            if drafts:
                picked = await db.execute_fetchall("SELECT player_id FROM draft_picks WHERE draft_id=?", (drafts[0]["id"],))
                picked_set = {p["player_id"] for p in picked}
        finally:
            await db.close()

        result = []
        for pid in queue_ids:
            p = await fetch_player(pid)
            if p:
                p["available"] = pid not in picked_set
                result.append(p)
        return result

    # Fallback: local DB
    from src.backend.database import get_db
    db = await get_db()
    try:
        placeholders = ",".join("?" for _ in queue_ids)
        rows = await db.execute_fetchall(
            f"SELECT * FROM players WHERE id IN ({placeholders})", queue_ids
        )
        player_map = {r["id"]: dict(r) for r in rows}
        drafts = await db.execute_fetchall("SELECT id FROM drafts WHERE league_id=?", (league_id,))
        picked_set = set()
        if drafts:
            picked = await db.execute_fetchall("SELECT player_id FROM draft_picks WHERE draft_id=?", (drafts[0]["id"],))
            picked_set = {p["player_id"] for p in picked}

        result = []
        for pid in queue_ids:
            p = player_map.get(pid)
            if p:
                p["available"] = pid not in picked_set
                result.append(p)
        return result
    finally:
        await db.close()


@router.post("/leagues/{league_id}/draft/queue/add")
async def add_to_queue(league_id: str, body: DraftPickRequest, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    await DraftEngine.add_to_queue(league_id, auth["team_id"], body.player_id)
    # If it's my turn and I have a queue, process
    await _process_and_broadcast_autodraft(league_id)
    return {"ok": True, "queue": await DraftEngine.get_queue(league_id, auth["team_id"])}


@router.post("/leagues/{league_id}/draft/queue/remove")
async def remove_from_queue(league_id: str, body: DraftPickRequest, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    await DraftEngine.remove_from_queue(league_id, auth["team_id"], body.player_id)
    return {"ok": True, "queue": await DraftEngine.get_queue(league_id, auth["team_id"])}


@router.post("/leagues/{league_id}/draft/queue/reorder")
async def reorder_queue(league_id: str, body: dict, auth: dict = Depends(get_current_team)):
    """Set the full queue order. Body: {"queue": ["player_id_1", "player_id_2", ...]}"""
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    await DraftEngine.set_queue(league_id, auth["team_id"], body.get("queue", []))
    return {"ok": True, "queue": await DraftEngine.get_queue(league_id, auth["team_id"])}


@router.post("/leagues/{league_id}/draft/queue/clear")
async def clear_queue(league_id: str, auth: dict = Depends(get_current_team)):
    if auth["league_id"] != league_id:
        raise HTTPException(403, "Not in this league")
    await DraftEngine.clear_queue(league_id, auth["team_id"])
    return {"ok": True, "queue": []}


async def _process_and_broadcast_autodraft(league_id: str):
    """Process autodraft picks and broadcast each one."""
    import asyncio
    auto_results = await DraftEngine.process_autodraft(league_id)
    for pick in auto_results:
        state = await DraftEngine.get_draft_state(league_id)
        await _broadcast(league_id, {
            "type": "pick" if state and state["status"] == "in_progress" else "draft_end",
            "pick": pick,
            "state": state,
            "autodraft": True,
        })
        # Delay between autodraft picks so clients can follow progress
        await asyncio.sleep(1.0)


@router.websocket("/leagues/{league_id}/draft/ws")
async def draft_websocket(websocket: WebSocket, league_id: str):
    await websocket.accept()
    if league_id not in _draft_connections:
        _draft_connections[league_id] = []
    _draft_connections[league_id].append(websocket)

    try:
        # Send current state on connect
        state = await DraftEngine.get_draft_state(league_id)
        if state:
            await websocket.send_json({"type": "state", "state": state})

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "pick":
                # Client-side picks go through REST, WS is read-only for broadcast
                pass
    except WebSocketDisconnect:
        pass
    finally:
        conns = _draft_connections.get(league_id, [])
        if websocket in conns:
            conns.remove(websocket)
