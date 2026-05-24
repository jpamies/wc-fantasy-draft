import asyncio
import json
from datetime import datetime, timezone
try:
    from pywebpush import webpush, WebPushException
except Exception:  # pragma: no cover - fallback for environments missing pywebpush
    webpush = None

    class WebPushException(Exception):
        pass

from src.backend.config import settings
from src.backend.database import get_db


def push_enabled() -> bool:
    return bool(
        webpush
        and settings.PUSH_VAPID_PUBLIC_KEY
        and settings.PUSH_VAPID_PRIVATE_KEY
        and settings.PUSH_VAPID_SUBJECT
    )


async def upsert_push_subscription(team_id: str, endpoint: str, p256dh_key: str, auth_key: str, user_agent: str = ""):
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO push_subscriptions (team_id, endpoint, p256dh_key, auth_key, user_agent, is_active, updated_at)
            VALUES ($1, $2, $3, $4, $5, 1, $6)
            ON CONFLICT (endpoint) DO UPDATE SET
                team_id = EXCLUDED.team_id,
                p256dh_key = EXCLUDED.p256dh_key,
                auth_key = EXCLUDED.auth_key,
                user_agent = EXCLUDED.user_agent,
                is_active = 1,
                updated_at = EXCLUDED.updated_at
            """,
            (team_id, endpoint, p256dh_key, auth_key, user_agent, now),
        )
        await db.commit()
    finally:
        await db.close()


async def deactivate_push_subscription(team_id: str, endpoint: str | None = None):
    db = await get_db()
    try:
        if endpoint:
            await db.execute(
                "UPDATE push_subscriptions SET is_active=0, updated_at=$3 WHERE team_id=$1 AND endpoint=$2",
                (team_id, endpoint, datetime.now(timezone.utc).isoformat()),
            )
        else:
            await db.execute(
                "UPDATE push_subscriptions SET is_active=0, updated_at=$2 WHERE team_id=$1",
                (team_id, datetime.now(timezone.utc).isoformat()),
            )
        await db.commit()
    finally:
        await db.close()


async def send_push_to_team(team_id: str, title: str, body: str, data: dict | None = None, tag: str | None = None) -> dict:
    if not push_enabled():
        return {"disabled": True, "sent": 0, "failed": 0}

    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """
            SELECT endpoint, p256dh_key, auth_key
            FROM push_subscriptions
            WHERE team_id=$1 AND is_active=1
            """,
            (team_id,),
        )

        if not rows:
            return {"disabled": False, "sent": 0, "failed": 0}

        payload = json.dumps({
            "title": title,
            "body": body,
            "tag": tag,
            "data": data or {},
        })

        sent = 0
        failed = 0
        now = datetime.now(timezone.utc).isoformat()

        for row in rows:
            endpoint = row["endpoint"]
            sub_info = {
                "endpoint": endpoint,
                "keys": {
                    "p256dh": row["p256dh_key"],
                    "auth": row["auth_key"],
                },
            }

            try:
                await asyncio.to_thread(
                    webpush,
                    subscription_info=sub_info,
                    data=payload,
                    vapid_private_key=settings.PUSH_VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": settings.PUSH_VAPID_SUBJECT},
                    ttl=60,
                )
                await db.execute(
                    """
                    UPDATE push_subscriptions
                    SET failure_count=0, last_success_at=$2, updated_at=$2
                    WHERE endpoint=$1
                    """,
                    (endpoint, now),
                )
                sent += 1
            except WebPushException as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in (404, 410):
                    await db.execute(
                        """
                        UPDATE push_subscriptions
                        SET is_active=0, failure_count=failure_count+1, last_failure_at=$2, updated_at=$2
                        WHERE endpoint=$1
                        """,
                        (endpoint, now),
                    )
                else:
                    await db.execute(
                        """
                        UPDATE push_subscriptions
                        SET failure_count=failure_count+1, last_failure_at=$2, updated_at=$2
                        WHERE endpoint=$1
                        """,
                        (endpoint, now),
                    )
                failed += 1
            except Exception:
                await db.execute(
                    """
                    UPDATE push_subscriptions
                    SET failure_count=failure_count+1, last_failure_at=$2, updated_at=$2
                    WHERE endpoint=$1
                    """,
                    (endpoint, now),
                )
                failed += 1

        await db.commit()
        return {"disabled": False, "sent": sent, "failed": failed}
    finally:
        await db.close()
