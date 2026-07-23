"""MOEX (Московская биржа) data source — public, no-auth.

This module provides a drop-in alternative to the paid ``AigenisClient`` for
markets available on MOEX ISS without authentication:

* RUB corporate bonds — board ``TQCB``
* USD/EUR eurobonds — board ``TQOB`` (currency taken from ``FACEUNIT``)

It exposes a small client implementing the same surface the pipeline expects
(``fetch_listing`` / ``fetch_detail`` / ``fetch_history``) but returns
ready-to-persist ``Bond`` models directly, so no aigenis.by-specific parsers are
involved. Enable via ``DATA_SOURCE=moex`` (or ``both`` to merge with the
primary source).

Rate limits: MOEX ISS is public but please keep concurrency modest.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx

from scraper.config import get_settings
from scraper.logging import get_logger
from scraper.models import Bond, BondHistory, CouponFrequency

logger = get_logger("scraper.moex")

MOEX_ISS_BASE = "https://iss.moex.com/iss"

# Default boards. TQCB = RUB corporates, TQOB = USD/EUR eurobonds.
_DEFAULT_BOARDS = ["TQCB", "TQOB"]


def _boards() -> list[str]:
    raw = os.getenv("MOEX_BOARDS", "").strip()
    if raw:
        return [b.strip().upper() for b in raw.split(",") if b.strip()]
    return list(_DEFAULT_BOARDS)


def _freq_from_annual(per_year: Any) -> CouponFrequency | None:
    try:
        n = int(per_year)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if n in (1, 2, 4, 12):
        return n  # type: ignore[return-value]
    return None


def _to_dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def _to_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# MOEX FACEUNIT uses 'SUR' for Russian ruble; normalize to our Currency literal.
_CURRENCY_ALIASES = {
    "SUR": "RUB",
    "RUR": "RUB",
    "RUB": "RUB",
    "USD": "USD",
    "EUR": "EUR",
    "BYN": "BYN",
    "GBP": "USD",  # treat as USD-denominated for storage simplicity
}


def _norm_currency(value: Any) -> str:
    return _CURRENCY_ALIASES.get(str(value or "").upper(), "RUB")


def _parse_iss_rows(payload: dict[str, Any], block: str) -> list[dict[str, Any]]:
    node = payload.get(block)
    if not node:
        return []
    columns = node.get("columns", [])
    rows = node.get("data", [])
    return [dict(zip(columns, row, strict=False)) for row in rows]


class MoexClient:
    """Public MOEX ISS client. Implements the pipeline-facing surface.

    Unlike ``AigenisClient``, listing/detail/history return ``Bond``/history
    records directly (not raw aigenis.by payloads), so the pipeline can persist
    them without the aigenis-specific parsers.
    """

    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._boards = _boards()
        self._cap = int(os.getenv("MOEX_CAP", "1000"))
        self._timeout = float(os.getenv("MOEX_TIMEOUT", "30"))
        self._id_by_internal: dict[str, str] = {}

    async def __aenter__(self) -> MoexClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    # --- listing ----------------------------------------------------------
    async def fetch_listing(self, currency: str) -> list[dict[str, Any]]:
        """Return rows shaped like aigenis listing payloads."""
        bonds = await self.fetch_bonds(currency)
        return [
            {"internal_id": b.internal_id, "currency": b.currency, "name": b.name}
            for b in bonds
        ]

    async def fetch_bonds(self, currency: str | None = None) -> list[Bond]:
        """Fetch bonds across configured boards as ``Bond`` models."""
        wanted = currency.upper() if currency else None
        out: list[Bond] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for board in self._boards:
                try:
                    rows = await self._fetch_board(client, board)
                except Exception as exc:
                    logger.warning("moex_board_failed", board=board, error=str(exc))
                    continue
                for row in rows:
                    if wanted and row.currency != wanted:
                        continue
                    out.append(row)
                    if len(out) >= self._cap:
                        break
                if len(out) >= self._cap:
                    break
        logger.info("moex_bonds_fetched", count=len(out), boards=self._boards)
        return out

    async def _fetch_board(self, client: httpx.AsyncClient, board: str) -> list[Bond]:
        url = (
            f"{MOEX_ISS_BASE}/engines/stock/markets/bonds/boards/{board}"
            f"/securities.json?iss.meta=off"
            f"&iss.only=securities,marketdata,securities_columns"
        )
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()
        securities = _parse_iss_rows(payload, "securities")
        marketdata = {
            r.get("SECID"): r for r in _parse_iss_rows(payload, "marketdata")
        }
        bonds: list[Bond] = []
        for sec in securities:
            secid = sec.get("SECID")
            if not secid:
                continue
            md = marketdata.get(secid, {})
            cur = _norm_currency(sec.get("FACEUNIT") or "RUB")
            internal_id = f"MOEX_{secid}"
            self._id_by_internal[internal_id] = secid
            try:
                bond = Bond(
                    internal_id=internal_id,
                    name=str(sec.get("SECNAME") or secid),
                    issuer=sec.get("ISSUER") or sec.get("SHORTNAME"),
                    currency=cur,  # type: ignore[arg-type]
                    nominal=_to_dec(sec.get("FACEVALUE")),
                    coupon_rate=_to_dec(sec.get("COUPONVALUE")),
                    coupon_frequency=_freq_from_annual(sec.get("COUPONPERIOD")),
                    maturity_date=_to_date(sec.get("MATDATE")),
                    price=_to_dec(md.get("LAST")),
                    yield_to_maturity=_to_dec(md.get("YIELD")),
            isin=sec.get("ISIN"),
            status="active",
            is_government=bool(
                sec.get("ISIN")
                and str(sec.get("ISIN")).startswith("RU")
                and "GOV" in str(sec.get("SHORTNAME", "")).upper()
            ),
            fetched_at=datetime.now(UTC),
        )
                bonds.append(bond)
            except Exception as exc:
                logger.warning("moex_bond_parse_failed", secid=secid, error=str(exc))
        return bonds

    # --- detail -----------------------------------------------------------
    async def fetch_detail(self, internal_id: str) -> Bond:
        """Return a single bond by its MOEX-derived internal id."""
        secid = self._id_by_internal.get(internal_id)
        if secid is None and internal_id.startswith("MOEX_"):
            secid = internal_id[len("MOEX_"):]
        if secid is None:
            from scraper.errors import NotFoundError

            raise NotFoundError(f"Unknown MOEX bond {internal_id}")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            url = (
                f"{MOEX_ISS_BASE}/engines/stock/markets/bonds/boards/TQCB"
                f"/securities/{secid}.json?iss.meta=off"
                f"&iss.only=securities,marketdata"
            )
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
            securities = _parse_iss_rows(payload, "securities")
            if not securities:
                url2 = url.replace("/boards/TQCB/", "/boards/TQOB/")
                resp2 = await client.get(url2)
                resp2.raise_for_status()
                securities = _parse_iss_rows(resp2.json(), "securities")
            md = {r.get("SECID"): r for r in _parse_iss_rows(payload, "marketdata")}
            sec = securities[0]
            md_row = md.get(secid, {})
            cur = _norm_currency(sec.get("FACEUNIT") or "RUB")
            return Bond(
                internal_id=internal_id,
                name=str(sec.get("SECNAME") or secid),
                issuer=sec.get("ISSUER") or sec.get("SHORTNAME"),
                currency=cur,  # type: ignore[arg-type]
                nominal=_to_dec(sec.get("FACEVALUE")),
                coupon_rate=_to_dec(sec.get("COUPONVALUE")),
                coupon_frequency=_freq_from_annual(sec.get("COUPONPERIOD")),
                maturity_date=_to_date(sec.get("MATDATE")),
                price=_to_dec(md_row.get("LAST")),
                yield_to_maturity=_to_dec(md_row.get("YIELD")),
                isin=sec.get("ISIN"),
                status="active",
                fetched_at=datetime.now(UTC),
            )

    # --- history ----------------------------------------------------------
    async def fetch_history(self, internal_id: str, _days: int = 30) -> list[BondHistory]:
        """Fetch daily close+YTM history for a bond (charts / accruals).

        Uses MOEX ``/history/.../candles`` (one row per trading day) so the
        product gets real price history without the paid source. Tries the
        board matching the bond's currency, then the other board as fallback.
        """
        secid = self._id_by_internal.get(internal_id)
        if secid is None and internal_id.startswith("MOEX_"):
            secid = internal_id[len("MOEX_"):]
        if secid is None:
            return []
        # Try both boards: eurobonds live on TQOB, corporates on TQCB.
        boards = ["TQOB", "TQCB"] if internal_id.upper().endswith(("USD", "EUR")) else ["TQCB", "TQOB"]
        history: list[BondHistory] = []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                for board in boards:
                    url = (
                        f"{MOEX_ISS_BASE}/history/engines/stock/markets/bonds/boards/{board}"
                        f"/securities/{secid}/candles.json?iss.meta=off&interval=24"
                    )
                    try:
                        resp = await client.get(url)
                        resp.raise_for_status()
                        payload = resp.json()
                    except Exception:
                        continue
                    candles = _parse_iss_rows(payload, "history")
                    for c in candles:
                        d = _to_date(c.get("TRADEDATE"))
                        close = _to_dec(c.get("CLOSE"))
                        ytm = _to_dec(c.get("YIELDCLOSE"))
                        if d and (close is not None or ytm is not None):
                            try:
                                history.append(
                                    BondHistory(
                                        internal_id=internal_id,
                                        date=d,
                                        price=close,
                                        yield_=ytm,
                                        status="active",
                                    )
                                )
                            except Exception:
                                continue
                    if history:
                        break
                logger.info("moex_history_fetched", secid=secid, count=len(history))
                return history
        except Exception as exc:
            logger.warning("moex_history_failed", secid=secid, error=str(exc))
            return []

    async def fetch_coupons(self, internal_id: str) -> list[dict[str, Any]]:
        """Fetch the coupon calendar (payment dates + amounts) from MOEX.

        Uses the bondization endpoint (``/securities/{secid}/bondization.json``,
        ``coupons`` block). Returns lightweight dicts with ``date`` (coupondate)
        and ``coupon`` (value). Best-effort: returns [] on any failure.
        """
        secid = self._id_by_internal.get(internal_id)
        if secid is None and internal_id.startswith("MOEX_"):
            secid = internal_id[len("MOEX_"):]
        if secid is None:
            return []
        url = f"{MOEX_ISS_BASE}/securities/{secid}/bondization.json?iss.meta=off"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                payload = resp.json()
                rows = _parse_iss_rows(payload, "coupons")
                out = []
                for r in rows:
                    d = _to_date(r.get("coupondate"))
                    val = _to_dec(r.get("value"))
                    if d:
                        out.append({"date": d, "coupon": val})
                if out:
                    logger.info("moex_coupons_fetched", secid=secid, count=len(out))
                return out
        except Exception as exc:
            logger.warning("moex_coupons_failed", secid=secid, error=str(exc))
            return []
