from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request

from src.backend.auth import get_current_team
from src.backend.config import settings
from src.backend.services.push_service import (
    push_enabled,
    upsert_push_subscription,
    deactivate_push_subscription,
    send_push_to_team,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


class PushSubscriptionBody(BaseModel):
    subscription: dict


class PushUnsubscribeBody(BaseModel):
    endpoint: str | None = None


@router.get("/push/public-key")
async def get_push_public_key(auth: dict = Depends(get_current_team)):
    if not auth.get("team_id"):
        raise HTTPException(403, "Not authenticated")
    return {
        "enabled": push_enabled(),
        "public_key": settings.PUSH_VAPID_PUBLIC_KEY if push_enabled() else "",
    }


@router.post("/push/subscribe")
async def subscribe_push(body: PushSubscriptionBody, request: Request, auth: dict = Depends(get_current_team)):
    sub = body.subscription or {}
    endpoint = sub.get("endpoint")
    keys = sub.get("keys") or {}
    p256dh_key = keys.get("p256dh")
    auth_key = keys.get("auth")

    if not endpoint or not p256dh_key or not auth_key:
        raise HTTPException(400, "Invalid push subscription payload")

    await upsert_push_subscription(
        team_id=auth["team_id"],
        endpoint=endpoint,
        p256dh_key=p256dh_key,
        auth_key=auth_key,
        user_agent=request.headers.get("user-agent", ""),
    )
    return {"ok": True}


@router.post("/push/unsubscribe")
async def unsubscribe_push(body: PushUnsubscribeBody, auth: dict = Depends(get_current_team)):
    await deactivate_push_subscription(auth["team_id"], body.endpoint)
    return {"ok": True}


@router.post("/push/test")
async def test_push(auth: dict = Depends(get_current_team)):
    result = await send_push_to_team(
        team_id=auth["team_id"],
        title="WC Fantasy",
        body="Push de prueba enviado correctamente",
        data={"type": "push-test", "url": "/#/"},
        tag="push-test",
    )
    return {"ok": True, **result}
