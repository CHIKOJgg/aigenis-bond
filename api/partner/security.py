"""Partner API authentication and rate limiting.

Partners authenticate with a static API key sent in the ``X-Aigenis-Api-Key``
header. The key is hashed with bcrypt before storage (see ``PartnerKeyORM``), so
a database leak cannot expose live credentials. Each key carries its own
per-minute rate budget (``rate_limit``), enforced independently of the
user/IP limiter in ``api.main``.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import defaultdict

import bcrypt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select

from scraper.db import session_scope
from scraper.orm import PartnerKeyORM

_KEY_PREFIX = "ak_"
_WINDOW_SECONDS = 60


def generate_api_key() -> tuple[str, str]:
    """Return ``(raw_key, key_hash)``. The raw key is shown only once."""
    raw = _KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def get_partner_key(
    x_aigenis_api_key: str | None = Header(default=None, alias="X-Aigenis-Api-Key"),
) -> PartnerKeyORM:
    if not x_aigenis_api_key:
        raise HTTPException(status_code=401, detail="Missing X-Aigenis-Api-Key header")
    # bcrypt hash is salted — iterate through active keys and verify one by one.
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(PartnerKeyORM).where(PartnerKeyORM.active.is_(True))
            )
        ).scalars().all()
    for key in rows:
        try:
            if bcrypt.checkpw(x_aigenis_api_key.encode("utf-8"), key.key_hash.encode("utf-8")):
                return key
        except (ValueError, Exception):
            continue
    raise HTTPException(status_code=401, detail="Invalid or inactive API key")


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
