"""Fallback quote source (diversification of data dependency).

The primary scraper (``scraper.client.AigenisClient``) depends on a paid login
to the source site. To keep the product running "without investments" even when
those credentials are unavailable, this module defines a pluggable interface
for an alternative public quote source.

It is intentionally a thin stub: implementing a concrete adapter requires
choosing a specific public data provider and respecting its terms/rate limits.
Wire it in via the ``FALLBACK_SOURCE`` env var and call ``fetch_fallback_bonds``
from the pipeline when the primary source is unavailable.

Interface contract
------------------
A fallback source yields lightweight bond quotes with at least:
``internal_id, name, currency, yield_to_maturity, price, maturity_date, issuer``.
"""
from __future__ import annotations

import os
from typing import Any

from scraper.logging import get_logger

logger = get_logger("scraper.fallback_source")

_FALLBACK_SOURCE = os.getenv("FALLBACK_SOURCE", "").strip().lower()


def fallback_source_name() -> str | None:
    """Return the configured fallback source name, or None if disabled."""
    return _FALLBACK_SOURCE or None


async def fetch_fallback_bonds(currency: str | None = None) -> list[dict[str, Any]]:
    """Fetch bond quotes from the configured fallback source.

    Returns an empty list when no fallback is configured or the adapter is not
    yet implemented, so callers can degrade gracefully (serve stale DB data).
    """
    if not _FALLBACK_SOURCE:
        return []
    # Adapter dispatch. Add concrete implementations here, e.g.:
    #   if _FALLBACK_SOURCE == "public_x":
    #       return await _fetch_from_public_x(currency)
    logger.warning(
        "fallback_source_not_implemented",
        source=_FALLBACK_SOURCE,
        detail="no adapter registered — serve stale DB data",
    )
    return []
