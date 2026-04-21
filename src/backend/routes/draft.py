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
    state = await DraftEngine.get_draft_state(league_id)
    await _broadcast(league_id, {"type": "draft_started", "state": state})
    return result


@router.get("/leagues/{league_id}/draft")
async def get_draft(league_id: str):
    state = await DraftEngine.get_draft_state(league_id)
    if not state:
        raise HTTPException(404, "No draft found")
    return state


@router.get("/leagues/{league_id}/draft/available")
async def get_available(league_id: str, position: str | None = None, search: str | None = None):
    return await DraftEngine.get_available_players(league_id, position, search)


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
    return result


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
