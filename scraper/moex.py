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

from desk.ytm import sane_yield, ytm_from_price
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


def _freq_from_coupon_period(value: Any) -> CouponFrequency | None:
    """Coupon frequency from MOEX's COUPONPERIOD field.

    MOEX ISS documents COUPONPERIOD in *days* (e.g. 182 = semi-annual).
    Accept the per-year counts (1/2/4/12) for robustness, then map day
    ranges to the nearest standard frequency.
    """
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if n in (1, 2, 4, 12):
        return n  # type: ignore[return-value]
    if 360 <= n <= 370:
        return 1
    if 180 <= n <= 185:
        return 2
    if 88 <= n <= 95:
        return 4
    if 28 <= n <= 32:
        return 12
    return None


def _moex_status(securities: dict, marketdata: dict | None) -> str:
    """Определить статус облигации по данным MOEX ISS."""
    board = str(securities.get("BOARDID", "")).upper()
    if board in ("TQCB", "TQOB"):
        if marketdata:
            traded = str(marketdata.get("LCLOSE", "")).strip()
            last = str(marketdata.get("LAST", "")).strip()
            if traded or last:
                return "active"
        return "active"
    return "unknown"


def _to_dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def _coupon_rate_pct(sec: dict) -> Decimal | None:
    """Coupon rate in % per annum.

    MOEX ISS securities block exposes TWO coupon fields:
      - COUPONVALUE  — coupon AMOUNT in face-currency per bond per period
        (e.g. 8.38 RUB on a 750-RUB face) — NOT a rate.
      - COUPONPERCENT — annual coupon RATE in percent (e.g. 13.6 = 13.6%).
    The engine/UI treat coupon_rate as an annual % (percent points), so we
    must use COUPONPERCENT when present and only fall back to a derived
    amount-based estimate when the rate is missing.
    """
    pct = _to_dec(sec.get("COUPONPERCENT"))
    if pct is not None and pct > 0:
        return pct
    amount = _to_dec(sec.get("COUPONVALUE"))
    face = _to_dec(sec.get("FACEVALUE"))
    period = sec.get("COUPONPERIOD")
    if amount is None or face is None or face <= 0 or period is None:
        return None
    try:
        period_days = int(period)
    except (TypeError, ValueError):
        return None
    if period_days <= 0:
        return None
    per_period_pct = float(amount) / float(face) * 100.0
    annual_pct = per_period_pct * (365.0 / period_days)
    return Decimal(str(round(annual_pct, 4)))


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


def _quote_and_yield(
    sec: dict[str, Any], md: dict[str, Any]
) -> tuple[Decimal | None, Decimal | None]:
    """Return a (price, YTM) pair that survives the sanity check.

    MOEX ISS reports YIELD for untraded paper as garbage (negative or absurd
    values like 1374%), so the yield is only trusted when a price exists and
    it is within ``MOEX_YTM_SANITY_TOL_PP`` percentage points of the yield the
    coupon schedule implies; otherwise we fall back to our own Newton-Raphson
    estimate, or None so downstream can honestly show "no data".
    """
    price = (
        _to_dec(md.get("LAST"))
        or _to_dec(md.get("LCLOSEPRICE"))
        or _to_dec(md.get("MARKETPRICE"))
    )
    if price is None or price <= 0:
        return None, None
    coupon = _coupon_rate_pct(sec)
    freq = _freq_from_coupon_period(sec.get("COUPONPERIOD"))
    maturity = _to_date(sec.get("MATDATE"))
    computed: float | None = None
    if coupon is not None and coupon > 0 and freq and maturity:
        computed = ytm_from_price(
            price_pct=float(price),
            coupon_rate_pct=float(coupon),
            coupon_frequency=int(freq),
            maturity=maturity,
        )
    ytm = _to_dec(md.get("YIELD"))
    if ytm is not None and sane_yield(float(ytm), computed):
        return price, ytm
    if computed is not None and computed > 0:
        return price, Decimal(str(round(computed, 4)))
    return price, None


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
            {"internal_id": b.internal_id, "currency": b.currency, "name": b.name} for b in bonds
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
        marketdata = {r.get("SECID"): r for r in _parse_iss_rows(payload, "marketdata")}
        bonds: list[Bond] = []
        for sec in securities:
            secid = sec.get("SECID")
            if not secid:
                continue
            name = str(sec.get("SECNAME") or secid)
            # Structured notes (e.g. «СФО БКС Структурные Ноты N») have
            # index/trigger-linked payoffs — pricing them with the plain-bond
            # YTM formula produces meaningless "opportunities" (a 75-price
            # note maturing in days showing 66% YTM). Skip them entirely.
            if "структурн" in name.lower():
                continue
            md = marketdata.get(secid, {})
            cur = _norm_currency(sec.get("FACEUNIT") or "RUB")
            internal_id = f"MOEX_{secid}"
            self._id_by_internal[internal_id] = secid
            price, ytm = _quote_and_yield(sec, md)
            try:
                bond = Bond(
                    internal_id=internal_id,
                    name=str(sec.get("SECNAME") or secid),
                    issuer=sec.get("ISSUER") or sec.get("SHORTNAME"),
                    currency=cur,  # type: ignore[arg-type]
                    nominal=_to_dec(sec.get("FACEVALUE")),
                    coupon_rate=_coupon_rate_pct(sec),
                    coupon_frequency=_freq_from_coupon_period(sec.get("COUPONPERIOD")),
                    maturity_date=_to_date(sec.get("MATDATE")),
                    price=price,
                    yield_to_maturity=ytm,
                    isin=sec.get("ISIN"),
                    market="moex",
                    status=_moex_status(sec, md),
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
            secid = internal_id[len("MOEX_") :]
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
            marketdata = {r.get("SECID"): r for r in _parse_iss_rows(payload, "marketdata")}
            if not securities:
                # Eurobonds live on TQOB — retry there and take its marketdata,
                # otherwise the price/YTM would silently be missing.
                url2 = url.replace("/boards/TQCB/", "/boards/TQOB/")
                resp2 = await client.get(url2)
                resp2.raise_for_status()
                payload2 = resp2.json()
                securities = _parse_iss_rows(payload2, "securities")
                marketdata = {r.get("SECID"): r for r in _parse_iss_rows(payload2, "marketdata")}
            sec = securities[0]
            md_row = marketdata.get(secid, {})
            cur = _norm_currency(sec.get("FACEUNIT") or "RUB")
            price, ytm = _quote_and_yield(sec, md_row)
            return Bond(
                internal_id=internal_id,
                name=str(sec.get("SECNAME") or secid),
                issuer=sec.get("ISSUER") or sec.get("SHORTNAME"),
                currency=cur,  # type: ignore[arg-type]
                nominal=_to_dec(sec.get("FACEVALUE")),
                coupon_rate=_coupon_rate_pct(sec),
                coupon_frequency=_freq_from_coupon_period(sec.get("COUPONPERIOD")),
                maturity_date=_to_date(sec.get("MATDATE")),
                price=price,
                yield_to_maturity=ytm,
                isin=sec.get("ISIN"),
                market="moex",
                status=_moex_status(sec, md_row),
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
            secid = internal_id[len("MOEX_") :]
        if secid is None:
            return []
        # Try both boards: eurobonds live on TQOB, corporates on TQCB.
        boards = (
            ["TQOB", "TQCB"] if internal_id.upper().endswith(("USD", "EUR")) else ["TQCB", "TQOB"]
        )
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
            secid = internal_id[len("MOEX_") :]
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
