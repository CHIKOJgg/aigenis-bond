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
import ipaddress
import json
import logging
import socket
from datetime import UTC, datetime
from urllib.parse import urlparse

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
    return hmac.HMAC(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


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


def _is_private_host(url: str) -> bool:
    """Block SSRF by rejecting webhook URLs pointing to private/loopback IPs."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    # Reject obvious private hostnames
    if host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return True
    if host.endswith((".local", ".internal", ".localhost")):
        return True
    # A literal IP address (v4 or v6) can be checked directly.
    try:
        ip = ipaddress.ip_address(host)
        if _is_private_ip(ip):
            return True
    except ValueError:
        pass
    # Resolve the hostname and check every address in ALL families (IPv4 + IPv6).
    try:
        addr = socket.getaddrinfo(host, 80, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return False
    for _family, _type, _proto, _canonname, sockaddr in addr:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _is_private_ip(ip):
            return True
    return False


def _is_private_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def deliver_webhook(wh: WebhookORM, event_type: str, payload: dict) -> bool:
    """POST a signed event to a single webhook. Returns True on 2xx."""
    # SSRF guard: reject private/loopback IPs, and pin the request to the
    # resolved public IP (with the original Host header) so a DNS-rebinding
    # attack cannot swap the target to an internal address after validation.
    parsed = urlparse(wh.url)
    host = parsed.hostname or ""
    pinned = _pin_public_ip(host)
    if pinned is None:
        return False
    target_host, _ = pinned
    req_url = wh.url.replace(host, target_host, 1) if host != target_host else wh.url

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
                req_url,
                content=body,
                headers={
                    "Host": host,
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


def _pin_public_ip(host: str) -> tuple[str, str] | None:
    """Resolve ``host`` to a public IP; return (ip, hostname) or None.

    ``None`` means the host resolves to a private/loopback/reserved address
    (or does not resolve) — the webhook must not be delivered.
    """
    if not host:
        return None
    try:
        ip = ipaddress.ip_address(host)
        if _is_private_ip(ip):
            return None
        return host, host
    except ValueError:
        pass
    try:
        addr = socket.getaddrinfo(host, 80, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        return None
    for family, _type, _proto, _canonname, sockaddr in addr:
        try:
            candidate = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if not _is_private_ip(candidate):
            ip = str(candidate)
            if family == socket.AF_INET6:
                ip = f"[{ip}]"
            return ip, host
    return None


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
