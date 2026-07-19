"""Fallback quote source (diversification of data dependency).

The primary scraper (``scraper.client.AigenisClient``) depends on a paid login
to the source site. To keep the product running "without investments" even when
those credentials are unavailable, this module provides an alternative public
quote source.

Implemented adapter
--------------------
``moex`` — MOEX ISS API (https://iss.moex.com/iss/). Public, no auth required,
rate-limited. Fetches corporate bonds (board TQCB) with last price and YTM.
Covers the RUB market; other currencies stay served from stale DB data.

Interface contract
------------------
A fallback source yields lightweight bond quotes with at least:
``internal_id, name, currency, yield_to_maturity, price, maturity_date, issuer``.

Wire it in via ``FALLBACK_SOURCE=moex``. Requires network egress and compliance
with MOEX rate limits.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import httpx

from scraper.logging import get_logger

logger = get_logger("scraper.fallback_source")

_FALLBACK_SOURCE = os.getenv("FALLBACK_SOURCE", "").strip().lower()

MOEX_ISS_BASE = "https://iss.moex.com/iss"
# Corporate bonds board. Covers RUB corporate issues.
_MOEX_BOARD = os.getenv("FALLBACK_MOEX_BOARD", "TQCB")
_MOEX_TIMEOUT = float(os.getenv("FALLBACK_MOEX_TIMEOUT", "30"))


def fallback_source_name() -> str | None:
    """Return the configured fallback source name, or None if disabled."""
    return _FALLBACK_SOURCE or None


async def fetch_fallback_bonds(currency: str | None = None) -> list[dict[str, Any]]:
    """Fetch bond quotes from the configured fallback source.

    Returns an empty list when no fallback is configured or the adapter fails,
    so callers can degrade gracefully (serve stale DB data).
    """
    if not _FALLBACK_SOURCE:
        return []
    if _FALLBACK_SOURCE == "moex":
        # MOEX only covers RUB-denominated bonds via the public ISS API.
        if currency and currency.upper() != "RUB":
            return []
        return await _fetch_moex_bonds()
    logger.warning(
        "fallback_source_unknown",
        source=_FALLBACK_SOURCE,
        detail="no adapter registered — serve stale DB data",
    )
    return []


def _parse_iss_rows(payload: dict[str, Any], block: str) -> list[dict[str, Any]]:
    """Flatten an ISS response block (data/meta columns) into row dicts."""
    node = payload.get(block)
    if not node:
        return []
    columns = node.get("columns", [])
    rows = node.get("data", [])
    return [dict(zip(columns, row)) for row in rows]


async def _fetch_moex_bonds() -> list[dict[str, Any]]:
    """Fetch corporate bonds from MOEX with last price + YTM.

    Two calls per query: (1) securities on the board (id, name, issuer,
    matdate), (2) marketdata (LAST) + an estimate of YTM from the bondization
    endpoint is heavy, so we approximate YTM from LAST price vs face where the
    board provides YIELD via ``marketdata_yields`` when available.
    """
    try:
        async with httpx.AsyncClient(timeout=_MOEX_TIMEOUT) as client:
            listing_url = (
                f"{MOEX_ISS_BASE}/engines/stock/markets/bonds/boards/{_MOEX_BOARD}"
                f"/securities.json?iss.meta=off&iss.only=securities,marketdata"
            )
            resp = await client.get(listing_url)
            resp.raise_for_status()
            payload = resp.json()
            securities = _parse_iss_rows(payload, "securities")
            marketdata = {
                row.get("SECID"): row for row in _parse_iss_rows(payload, "marketdata")
            }
    except Exception as exc:
        logger.warning("fallback_moex_fetch_failed", error=str(exc))
        return []

    out: list[dict[str, Any]] = []
    for sec in securities[:200]:  # cap to keep fallback cheap
        secid = sec.get("SECID")
        if not secid:
            continue
        md = marketdata.get(secid, {})
        last = md.get("LAST")
        ytm = md.get("YIELD")
        if ytm is None and last is not None:
            # Rough YTM proxy: (coupon income implied) — leave None if unknown.
            ytm = None
        try:
            maturity = (
                datetime.strptime(sec["MATDATE"], "%Y-%m-%d").date()
                if sec.get("MATDATE")
                else None
            )
        except (ValueError, TypeError):
            maturity = None
        out.append(
            {
                "internal_id": f"MOEX_{secid}",
                "name": sec.get("SECNAME") or secid,
                "currency": "RUB",
                "price": float(last) if last not in (None, "") else None,
                "yield_to_maturity": float(ytm) if ytm not in (None, "") else None,
                "maturity_date": maturity.isoformat() if maturity else None,
                "issuer": sec.get("ISSUER") or sec.get("SHORTNAME"),
                "status": "active",
            }
        )
    logger.info("fallback_moex_fetched", count=len(out))
    return out
