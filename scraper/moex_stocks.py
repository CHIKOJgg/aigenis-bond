"""MOEX (Московская биржа) stock data source — public, no-auth.

This module provides a free alternative to paid stock data APIs for
markets available on MOEX ISS without authentication:

* TQBR — основной режим торгов акциями (RUB)
* TQOD — долларовый режим (USD)
* TQDE — евро-режим (EUR)

It exposes ``MoexStockClient`` implementing the same pipeline surface
(``fetch_stocks`` / ``fetch_stock_detail`` / ``fetch_stock_history``)
returning ready-to-persist ``Stock`` / ``StockHistory`` models.

Enable via ``DATA_SOURCE=moex`` or ``STOCK_DATA_SOURCE=moex``.
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
from scraper.models import Stock, StockHistory

logger = get_logger("scraper.moex_stocks")

MOEX_ISS_BASE = "https://iss.moex.com/iss"

_STOCK_BOARDS = ["TQBR", "TQOD", "TQDE"]


def _stock_boards() -> list[str]:
    raw = os.getenv("MOEX_STOCK_BOARDS", "").strip()
    if raw:
        return [b.strip().upper() for b in raw.split(",") if b.strip()]
    return list(_STOCK_BOARDS)


def _to_dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
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


def _parse_iss_rows(payload: dict[str, Any], block: str) -> list[dict[str, Any]]:
    node = payload.get(block)
    if not node:
        return []
    columns = node.get("columns", [])
    rows = node.get("data", [])
    return [dict(zip(columns, row, strict=False)) for row in rows]


# MOEX uses ISS_BOARD to identify the trading board. The stock status
# field is IS_TRADED (1 = traded, 0 = not traded).
_BOARD_CURRENCY_MAP = {
    "TQBR": "RUB",
    "TQOD": "USD",
    "TQDE": "EUR",
}


class MoexStockClient:
    """Public MOEX ISS client for stock data.

    Returns ``Stock`` / ``StockHistory`` models directly — no third-party
    parsers involved. Enable via ``DATA_SOURCE=moex`` or
    ``STOCK_DATA_SOURCE=moex``.
    """

    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._boards = _stock_boards()
        self._cap = int(os.getenv("MOEX_STOCK_CAP", "500"))
        self._timeout = float(os.getenv("MOEX_TIMEOUT", "30"))
        self._id_by_secid: dict[str, str] = {}

    async def __aenter__(self) -> MoexStockClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def fetch_stocks(self, board: str | None = None) -> list[Stock]:
        """Fetch stocks across configured boards as ``Stock`` models."""
        boards = [board.upper()] if board else self._boards
        out: list[Stock] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for brd in boards:
                try:
                    rows = await self._fetch_board(client, brd)
                except Exception as exc:
                    logger.warning("moex_stock_board_failed", board=brd, error=str(exc))
                    continue
                out.extend(rows)
                if len(out) >= self._cap:
                    break
        logger.info("moex_stocks_fetched", count=len(out), boards=boards)
        return out[: self._cap]

    async def _fetch_board(self, client: httpx.AsyncClient, board: str) -> list[Stock]:
        url = (
            f"{MOEX_ISS_BASE}/engines/stock/markets/shares/boards/{board}"
            f"/securities.json?iss.meta=off"
            f"&iss.only=securities,marketdata"
        )
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()
        securities = _parse_iss_rows(payload, "securities")
        marketdata = {r.get("SECID"): r for r in _parse_iss_rows(payload, "marketdata")}
        stocks: list[Stock] = []
        for sec in securities:
            secid = sec.get("SECID")
            if not secid:
                continue
            md = marketdata.get(secid, {})
            internal_id = f"MOEX_{secid}"
            self._id_by_secid[internal_id] = secid
            try:
                is_traded = md.get("IS_TRADED", 1)
                status = "active" if is_traded == 1 else "suspended"
                stock = Stock(
                    internal_id=internal_id,
                    secid=secid,
                    name=str(sec.get("SECNAME") or secid),
                    isin=sec.get("ISIN"),
                    issuer=sec.get("ISSUER") or sec.get("SHORTNAME"),
                    board=board,
                    currency=_BOARD_CURRENCY_MAP.get(board, "RUB"),
                    lot_size=_to_int(sec.get("LOTSIZE")),
                    prev_price=_to_dec(md.get("PREVPRICE")),
                    price=_to_dec(md.get("LAST")),
                    open_price=_to_dec(md.get("OPEN")),
                    high_price=_to_dec(md.get("HIGH")),
                    low_price=_to_dec(md.get("LOW")),
                    close_price=_to_dec(md.get("CLOSE")),
                    volume=_to_int(md.get("VOLUME")),
                    value_traded=_to_dec(md.get("VALTODAY")),
                    market_capitalization=_to_dec(sec.get("ISSUESIZE")) and _to_dec(md.get("LAST")) and (
                        _to_dec(sec.get("ISSUESIZE")) or Decimal(0)
                    ) * (_to_dec(md.get("LAST")) or Decimal(0)),
                    pe_ratio=_to_dec(sec.get("P-E")),
                    pbr_ratio=_to_dec(sec.get("P/B")),
                    dividend_yield=_to_dec(sec.get("DIVYIELD")),
                    earnings_per_share=_to_dec(sec.get("EPS")),
                    sector=sec.get("SECTOR"),
                    status=status,
                    raw=sec,
                    fetched_at=datetime.now(UTC),
                )
                stocks.append(stock)
            except Exception as exc:
                logger.warning("moex_stock_parse_failed", secid=secid, error=str(exc))
        return stocks

    async def fetch_stock_detail(self, internal_id: str) -> Stock:
        """Return a single stock by its MOEX-derived internal id."""
        secid = self._id_by_secid.get(internal_id)
        if secid is None and internal_id.startswith("MOEX_"):
            secid = internal_id[len("MOEX_"):]
        if secid is None:
            from scraper.errors import NotFoundError

            raise NotFoundError(f"Unknown MOEX stock {internal_id}")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            url = (
                f"{MOEX_ISS_BASE}/engines/stock/markets/shares/boards/TQBR"
                f"/securities/{secid}.json?iss.meta=off"
                f"&iss.only=securities,marketdata"
            )
            resp = await client.get(url)
            resp.raise_for_status()
            payload = resp.json()
            securities = _parse_iss_rows(payload, "securities")
            if not securities:
                from scraper.errors import NotFoundError

                raise NotFoundError(f"MOEX stock {secid} not found")
            md = {r.get("SECID"): r for r in _parse_iss_rows(payload, "marketdata")}
            sec = securities[0]
            md_row = md.get(secid, {})
            is_traded = md_row.get("IS_TRADED", 1)
            return Stock(
                internal_id=internal_id,
                secid=secid,
                name=str(sec.get("SECNAME") or secid),
                isin=sec.get("ISIN"),
                issuer=sec.get("ISSUER") or sec.get("SHORTNAME"),
                board="TQBR",
                currency="RUB",
                lot_size=_to_int(sec.get("LOTSIZE")),
                prev_price=_to_dec(md_row.get("PREVPRICE")),
                price=_to_dec(md_row.get("LAST")),
                open_price=_to_dec(md_row.get("OPEN")),
                high_price=_to_dec(md_row.get("HIGH")),
                low_price=_to_dec(md_row.get("LOW")),
                close_price=_to_dec(md_row.get("CLOSE")),
                volume=_to_int(md_row.get("VOLUME")),
                value_traded=_to_dec(md_row.get("VALTODAY")),
                pe_ratio=_to_dec(sec.get("P-E")),
                pbr_ratio=_to_dec(sec.get("P/B")),
                dividend_yield=_to_dec(sec.get("DIVYIELD")),
                earnings_per_share=_to_dec(sec.get("EPS")),
                sector=sec.get("SECTOR"),
                status="active" if is_traded == 1 else "suspended",
                raw=sec,
                fetched_at=datetime.now(UTC),
            )

    async def fetch_stock_history(
        self, internal_id: str, _days: int = 30
    ) -> list[StockHistory]:
        """Fetch daily OHLCV history for a stock (charts / analytics).

        Uses MOEX ``/history/.../candles`` (one row per trading day).
        """
        secid = self._id_by_secid.get(internal_id)
        if secid is None and internal_id.startswith("MOEX_"):
            secid = internal_id[len("MOEX_"):]
        if secid is None:
            return []
        history: list[StockHistory] = []
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                url = (
                    f"{MOEX_ISS_BASE}/history/engines/stock/markets/shares/boards/TQBR"
                    f"/securities/{secid}/candles.json?iss.meta=off&interval=24"
                )
                resp = await client.get(url)
                resp.raise_for_status()
                payload = resp.json()
                candles = _parse_iss_rows(payload, "history")
                for c in candles:
                    d = _to_date(c.get("TRADEDATE"))
                    if not d:
                        continue
                    try:
                        history.append(
                            StockHistory(
                                internal_id=internal_id,
                                date=d,
                                open_price=_to_dec(c.get("OPEN")),
                                high_price=_to_dec(c.get("HIGH")),
                                low_price=_to_dec(c.get("LOW")),
                                close_price=_to_dec(c.get("CLOSE")),
                                volume=_to_int(c.get("VOLUME")),
                                value_traded=_to_dec(c.get("VALUE")),
                                weighted_avg_price=_to_dec(c.get("WAPRICE")),
                                status="active",
                            )
                        )
                    except Exception:
                        continue
                logger.info(
                    "moex_stock_history_fetched", secid=secid, count=len(history)
                )
                return history
        except Exception as exc:
            logger.warning("moex_stock_history_failed", secid=secid, error=str(exc))
            return []
