"""Partner API authentication and rate limiting.

Partners authenticate with a static API key sent in the ``X-Aigenis-Api-Key``
header. The key is hashed with bcrypt before storage (see ``PartnerKeyORM``), so
a database leak cannot expose live credentials. Each key carries its own
per-minute rate budget (``rate_limit``), enforced independently of the
user/IP limiter in ``api.main``.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict

import bcrypt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.db import session_scope
from scraper.orm import PartnerKeyORM

_KEY_PREFIX = "ak_"
_WINDOW_SECONDS = 60


def _key_fingerprint(raw: str) -> str:
    """Unsalted SHA-256 fingerprint used for fast key lookup.

    The fingerprint is NOT a credential by itself (bcrypt hash stays the
    authoritative verification), but lets us find the candidate key in one
    indexed query instead of bcrypt-checking every active key per request.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Return ``(raw_key, key_hash, key_fp)``. The raw key is shown only once."""
    raw = _KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, hash_api_key(raw), _key_fingerprint(raw)


def hash_api_key(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def verify_api_key(session: AsyncSession, raw: str) -> PartnerKeyORM | None:
    """Look up an active key by fingerprint and confirm it with one bcrypt check."""
    row = (
        await session.execute(
            select(PartnerKeyORM).where(
                PartnerKeyORM.key_fp == _key_fingerprint(raw),
                PartnerKeyORM.active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    try:
        if bcrypt.checkpw(raw.encode("utf-8"), row.key_hash.encode("utf-8")):
            return row
    except ValueError, TypeError:
        return None
    return None


async def get_partner_key(
    x_aigenis_api_key: str | None = Header(default=None, alias="X-Aigenis-Api-Key"),
) -> PartnerKeyORM:
    if not x_aigenis_api_key:
        raise HTTPException(status_code=401, detail="Missing X-Aigenis-Api-Key header")
    async with session_scope() as session:
        key = await verify_api_key(session, x_aigenis_api_key)
    if key is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return key


_partner_hits: dict[int, list[float]] = defaultdict(list)
_partner_lock = threading.Lock()
_MAX_TRACKED_PARTNERS = 1000  # prevent memory exhaustion


async def partner_rate_limit(key: PartnerKeyORM = Depends(get_partner_key)) -> PartnerKeyORM:
    """Enforce the partner key's per-minute quota (authenticates first).

    Uses a per-key lock to prevent race conditions under concurrent requests.
    """
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    with _partner_lock:
        # Periodic cleanup to prevent memory exhaustion
        if len(_partner_hits) > _MAX_TRACKED_PARTNERS:
            _partner_hits.clear()
        hits = _partner_hits[key.id]
        hits[:] = [t for t in hits if t > cutoff]
        if len(hits) >= key.rate_limit:
            raise HTTPException(
                status_code=429,
                detail="Partner rate limit exceeded",
                headers={"Retry-After": str(_WINDOW_SECONDS)},
            )
        hits.append(now)
    return key
