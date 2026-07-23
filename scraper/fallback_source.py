"""Fallback quote source (diversification of data dependency).

The primary scraper (``scraper.client.AigenisClient``) depends on a paid login
to the source site. To keep the product running "without investments" even when
those credentials are unavailable, this module provides an alternative public
quote source.

Implemented adapter
--------------------
``moex`` — MOEX ISS API (https://iss.moex.com/iss/). Public, no auth required,
rate-limited. Fetches bonds across several boards:

* ``TQCB`` — RUB corporate bonds (last price + YTM via ``marketdata_yields``).
* ``TQOB`` — USD/EUR eurobonds (currency taken from ``FACEUNIT`` in the
  securities block, so USD/EUR coverage works without the paid source login).

Other currencies stay served from stale DB data. Boards are configurable via
``FALLBACK_MOEX_BOARDS`` (comma-separated) for future expansion.

Interface contract
------------------
A fallback source yields lightweight bond quotes with at least:
``internal_id, name, currency, yield_to_maturity, price, maturity_date, issuer``.

Wire it in via ``FALLBACK_SOURCE=moex``. Requires network egress and compliance
with MOEX rate limits.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import httpx

from scraper.logging import get_logger

logger = get_logger("scraper.fallback_source")

_FALLBACK_SOURCE = os.getenv("FALLBACK_SOURCE", "").strip().lower()

MOEX_ISS_BASE = "https://iss.moex.com/iss"
# Default board. TQCB = RUB corporates. TQOB = USD/EUR eurobonds.
_MOEX_BOARD = os.getenv("FALLBACK_MOEX_BOARD", "TQCB")
# Boards scanned for the fallback. Comma-separated override via FALLBACK_MOEX_BOARDS
# (e.g. "TQCB,TQOB"). TQOB adds USD/EUR eurobond coverage without paid login.
_MOEX_BOARDS = [
    b.strip().upper()
    for b in os.getenv("FALLBACK_MOEX_BOARDS", "").split(",")
    if b.strip()
] or [_MOEX_BOARD]
_MOEX_TIMEOUT = float(os.getenv("FALLBACK_MOEX_TIMEOUT", "30"))
_MOEX_CAP = int(os.getenv("FALLBACK_MOEX_CAP", "1000"))


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
        # MOEX covers RUB corporates (TQCB) and USD/EUR eurobonds (TQOB) via the
        # public ISS API. Scan all configured boards and filter by currency
        # afterwards (cheap; also lets us discover FX units from FACEUNIT).
        return await _fetch_moex_bonds(currency)
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
    return [dict(zip(columns, row, strict=False)) for row in rows]


async def _fetch_moex_bonds(currency: str | None = None) -> list[dict[str, Any]]:
    """Fetch bonds from MOEX across configured boards with price + YTM.

    Scans every board in ``_MOEX_BOARDS``. Currency is taken from the
    securities block ``FACEUNIT`` field (RUB for TQCB, USD/EUR for TQOB), so
    USD/EUR eurobond coverage works without the paid source login. YTM comes
    from the ``YIELD`` marketdata column when available. Results are filtered
    to ``currency`` (if requested) after the boards are scanned.
    """
    wanted = currency.upper() if currency else None
    all_rows: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=_MOEX_TIMEOUT) as client:
            for board in _MOEX_BOARDS:
                listing_url = (
                    f"{MOEX_ISS_BASE}/engines/stock/markets/bonds/boards/{board}"
                    f"/securities.json?iss.meta=off"
                    f"&iss.only=securities,marketdata"
                )
                try:
                    resp = await client.get(listing_url)
                    resp.raise_for_status()
                    payload = resp.json()
                except Exception as exc:
                    logger.warning("fallback_moex_board_failed", board=board, error=str(exc))
                    continue
                securities = _parse_iss_rows(payload, "securities")
                marketdata = {
                    row.get("SECID"): row
                    for row in _parse_iss_rows(payload, "marketdata")
                }
                for sec in securities:
                    secid = sec.get("SECID")
                    if not secid:
                        continue
                    cur = str(sec.get("FACEUNIT") or "RUB").upper()
                    if wanted and cur != wanted:
                        continue
                    md = marketdata.get(secid, {})
                    last = md.get("LAST")
                    ytm = md.get("YIELD")
                    try:
                        maturity = (
                            datetime.strptime(sec["MATDATE"], "%Y-%m-%d").date()
                            if sec.get("MATDATE")
                            else None
                        )
                    except (ValueError, TypeError):
                        maturity = None
                    all_rows.append(
                        {
                            "internal_id": f"MOEX_{secid}",
                            "name": sec.get("SECNAME") or secid,
                            "currency": cur,
                            "price": float(last) if last not in (None, "") else None,
                            "yield_to_maturity": float(ytm) if ytm not in (None, "") else None,
                            "maturity_date": maturity.isoformat() if maturity else None,
                            "issuer": sec.get("ISSUER") or sec.get("SHORTNAME"),
                            "status": "active",
                        }
                    )
                    if len(all_rows) >= _MOEX_CAP:
                        break
                if len(all_rows) >= _MOEX_CAP:
                    break
    except Exception as exc:
        logger.warning("fallback_moex_fetch_failed", error=str(exc))
        return all_rows
    logger.info("fallback_moex_fetched", count=len(all_rows), boards=_MOEX_BOARDS)
    return all_rows
