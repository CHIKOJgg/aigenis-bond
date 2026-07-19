"""Partner API authentication and rate limiting.

Partners authenticate with a static API key sent in the ``X-Aigenis-Api-Key``
header. Only the SHA-256 hash of the key is stored (see ``PartnerKeyORM``), so
a database leak cannot expose live credentials. Each key carries its own
per-minute rate budget (``rate_limit``), enforced independently of the
user/IP limiter in ``api.main``.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict

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
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def get_partner_key(
    x_aigenis_api_key: str | None = Header(default=None, alias="X-Aigenis-Api-Key"),
) -> PartnerKeyORM:
    if not x_aigenis_api_key:
        raise HTTPException(status_code=401, detail="Missing X-Aigenis-Api-Key header")
    key_hash = hash_api_key(x_aigenis_api_key)
    async with session_scope() as session:
        row = (
            await session.execute(
                select(PartnerKeyORM).where(PartnerKeyORM.key_hash == key_hash)
            )
        ).scalar_one_or_none()
    if row is None or not row.active:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return row


_partner_hits: dict[int, list[float]] = defaultdict(list)


async def partner_rate_limit(key: PartnerKeyORM = Depends(get_partner_key)) -> PartnerKeyORM:
    """Enforce the partner key's per-minute quota (authenticates first)."""
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
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
