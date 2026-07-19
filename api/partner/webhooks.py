"""Partner webhook subscriptions and event dispatch.

Partners register HTTPS endpoints that receive signed JSON POSTs when a
subscribed event fires (bond updated, price alert triggered, analysis ready,
…). Each delivery is HMAC-SHA256 signed with the webhook's ``secret`` in the
``X-Aigenis-Signature`` header so the receiver can verify authenticity.

Dispatch is best-effort: failures are recorded on the webhook row and retried
by the partner on their side; we do not block the caller.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from scraper.db import session_scope
from scraper.orm import WebhookORM

logger = logging.getLogger("api.partner.webhooks")

SUPPORTED_EVENTS = frozenset(
    {
        "bond.updated",
        "alert.triggered",
        "analysis.ready",
        "price.crossed",
    }
)


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def register_webhook(
    *, partner_key_id: int, url: str, events: list[str], secret: str
) -> WebhookORM:
    async with session_scope() as session:
        wh = WebhookORM(
            partner_key_id=partner_key_id,
            url=url,
            events=list(events),
            secret=secret,
        )
        session.add(wh)
        await session.commit()
        await session.refresh(wh)
        return wh


async def list_webhooks(partner_key_id: int) -> list[WebhookORM]:
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(WebhookORM).where(WebhookORM.partner_key_id == partner_key_id)
            )
        ).scalars().all()
        return list(rows)


async def get_webhook(partner_key_id: int, webhook_id: int) -> WebhookORM | None:
    async with session_scope() as session:
        return (
            await session.execute(
                select(WebhookORM).where(
                    WebhookORM.id == webhook_id,
                    WebhookORM.partner_key_id == partner_key_id,
                )
            )
        ).scalar_one_or_none()


async def delete_webhook(partner_key_id: int, webhook_id: int) -> bool:
    async with session_scope() as session:
        wh = (
            await session.execute(
                select(WebhookORM).where(
                    WebhookORM.id == webhook_id,
                    WebhookORM.partner_key_id == partner_key_id,
                )
            )
        ).scalar_one_or_none()
        if wh is None:
            return False
        await session.delete(wh)
        await session.commit()
        return True


async def deliver_webhook(wh: WebhookORM, event_type: str, payload: dict) -> bool:
    """POST a signed event to a single webhook. Returns True on 2xx."""
    body = json.dumps(
        {
            "event": event_type,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    signature = sign_payload(wh.secret, body)
    error: str | None = None
    ok = False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                wh.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Aigenis-Event": event_type,
                    "X-Aigenis-Signature": f"sha256={signature}",
                },
            )
        ok = resp.status_code < 300
        if not ok:
            error = f"HTTP {resp.status_code}"
    except Exception as exc:
        error = str(exc)[:512]

    async with session_scope() as session:
        obj = await session.get(WebhookORM, wh.id)
        if obj is not None:
            if ok:
                obj.last_delivered_at = datetime.now(UTC)
                obj.last_error = None
            else:
                obj.last_error = error
            await session.commit()
    return ok


async def _safe_deliver(wh: WebhookORM, event_type: str, payload: dict) -> None:
    try:
        await deliver_webhook(wh, event_type, payload)
    except Exception:
        logger.exception("webhook_delivery_failed", webhook_id=wh.id)


async def emit_webhook_event(
    event_type: str, payload: dict, *, wait: bool = False
) -> int:
    """Deliver ``event_type`` to every active webhook subscribed to it.

    Returns the number of matching webhooks. With ``wait=True`` the deliveries
    are awaited (used by tests and synchronous callers); otherwise they run as
    background tasks so the caller is not blocked.
    """
    if event_type not in SUPPORTED_EVENTS:
        logger.warning("webhook_unsupported_event", event=event_type)
        return 0

    async with session_scope() as session:
        rows = (await session.execute(select(WebhookORM).where(WebhookORM.active.is_(True)))).scalars().all()
        targets = [wh for wh in rows if event_type in (wh.events or [])]

    tasks = [asyncio.create_task(_safe_deliver(wh, event_type, payload)) for wh in targets]
    if wait:
        await asyncio.gather(*tasks, return_exceptions=True)
    return len(targets)
