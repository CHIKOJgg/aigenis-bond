"""Tests for the MOEX ISS stock client (parsing, mapping, history)."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest

from scraper.moex_stocks import MoexStockClient, _parse_iss_rows, _stock_boards

_FIXTURES = Path(__file__).parent / "fixtures" / "moex_iss"

_PAYLOADS = {
    "boards/TQBR/securities.json": "listing_tqbr.json",
    "boards/TQOD/securities.json": "listing_tqod.json",
    "boards/TQDE/securities.json": "listing_tqde.json",
    "securities/LKOH.json": "listing_tqbr.json",
    "candles.json": "history_sber.json",
}

_fail_requests = False


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, url: str):
        if _fail_requests:
            raise RuntimeError("moex down")
        for key, filename in _PAYLOADS.items():
            if key in url:
                return _FakeResp(_load(filename))
        raise AssertionError(f"unexpected url: {url}")


@pytest.fixture(autouse=True)
def _patch_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    import scraper.moex_stocks as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda *a, **k: _FakeClient())


def _run(coro):
    return asyncio.run(coro)


def _make_client(boards: list[str] | None = None) -> MoexStockClient:
    client = MoexStockClient()
    if boards is not None:
        client._boards = boards
    return client


def test_parse_iss_rows() -> None:
    payload = {"securities": {"columns": ["A", "B"], "data": [[1, 2]]}}
    assert _parse_iss_rows(payload, "securities") == [{"A": 1, "B": 2}]
    assert _parse_iss_rows(payload, "missing") == []


def test_stock_boards_default() -> None:
    assert _stock_boards() == ["TQBR", "TQOD", "TQDE"]


def test_fetch_stocks_parses_tqbr() -> None:
    global _fail_requests
    _fail_requests = False
    client = _make_client(boards=["TQBR"])

    async def go() -> list:
        async with client:
            return await client.fetch_stocks()

    fetched = _run(go())
    assert len(fetched) == 4
    sber = next(s for s in fetched if s.secid == "SBER")
    assert sber.internal_id == "MOEX_SBER"
    assert sber.board == "TQBR"
    assert sber.currency == "RUB"
    assert sber.price == Decimal("258.15")
    assert sber.prev_price == Decimal("255.90")
    assert sber.lot_size == 10
    assert sber.isin == "RU0009029540"
    assert sber.sector == "Банки"
    assert sber.pe_ratio == Decimal("6.5")
    assert sber.pbr_ratio == Decimal("0.8")
    assert sber.dividend_yield == Decimal("8.2")
    assert sber.earnings_per_share == Decimal("23.1")
    assert sber.status == "active"
    assert sber.market_capitalization == Decimal("21586948318") * Decimal("258.15")


def test_fetch_stocks_suspended_when_not_traded() -> None:
    global _fail_requests
    _fail_requests = False
    client = _make_client(boards=["TQBR"])

    async def go() -> list:
        async with client:
            return await client.fetch_stocks()

    fetched = _run(go())
    yndx = next(s for s in fetched if s.secid == "YNDX")
    assert yndx.status == "suspended"
    assert yndx.price is None
    assert yndx.volume == 0


def test_fetch_stocks_maps_board_currencies() -> None:
    global _fail_requests
    _fail_requests = False
    client = _make_client(boards=["TQBR", "TQOD", "TQDE"])

    async def go() -> list:
        async with client:
            return await client.fetch_stocks()

    fetched = _run(go())
    assert len(fetched) == 7
    assert {s.currency for s in fetched if s.secid == "SBER"} == {"RUB", "USD", "EUR"}


def test_fetch_stocks_failure_returns_empty() -> None:
    global _fail_requests
    _fail_requests = True
    client = _make_client(boards=["TQBR"])

    async def go() -> list:
        async with client:
            return await client.fetch_stocks()

    assert _run(go()) == []


def test_fetch_stock_detail_after_listing() -> None:
    global _fail_requests
    _fail_requests = False
    client = _make_client(boards=["TQBR"])

    async def go() -> object:
        async with client:
            await client.fetch_stocks()
            return await client.fetch_stock_detail("MOEX_LKOH")

    detail = _run(go())
    assert detail.secid == "LKOH"
    assert detail.board == "TQBR"
    assert detail.price == Decimal("7121.00")
    assert detail.status == "active"


def test_fetch_stock_history_parses_candles() -> None:
    global _fail_requests
    _fail_requests = False
    client = _make_client(boards=["TQBR"])

    async def go() -> list:
        async with client:
            await client.fetch_stocks()
            return await client.fetch_stock_history("MOEX_SBER")

    rows = _run(go())
    assert len(rows) == 3
    latest = rows[0]
    assert latest.date.isoformat() == "2026-08-05"
    assert latest.close_price == Decimal("255.90")
    assert latest.weighted_avg_price == Decimal("256.14")
    assert latest.volume == 38123000


# --- run_once_moex_stocks pipeline ---------------------------------------- #


class _FakePipelineClient:
    _boards: list[str] = []

    def __init__(
        self,
        stocks: list,
        history: list | None = None,
        raise_fetch: bool = False,
    ) -> None:
        self._stocks = stocks
        self._history = history or []
        self._raise_fetch = raise_fetch

    async def __aenter__(self) -> _FakePipelineClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def fetch_stocks(self) -> list:
        if self._raise_fetch:
            raise RuntimeError("moex down")
        return self._stocks

    async def fetch_stock_history(self, internal_id: str, _days: int = 30) -> list:
        return self._history


def _fake_settings(stock_cfg) -> object:
    import types

    return types.SimpleNamespace(stock=stock_cfg)


def _stock_model(iid: str = "MOEX_SBER") -> object:
    from datetime import UTC
    from datetime import datetime as _dt

    from scraper.models import Stock

    return Stock(
        internal_id=iid,
        secid=iid.removeprefix("MOEX_"),
        name=f"Stock {iid}",
        currency="RUB",
        board="TQBR",
        price=Decimal("100"),
        fetched_at=_dt.now(UTC),
    )


def test_pipeline_disabled_when_stock_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from scraper import pipeline

    monkeypatch.setattr(
        "scraper.config.get_settings",
        lambda: _fake_settings(SimpleNamespace(enabled=False)),
    )
    summary = _run(pipeline.run_once_moex_stocks())
    assert summary["skipped"] == 1
    assert summary["stocks_saved"] == 0


def test_pipeline_error_budget_stops_hammering(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from scraper import pipeline

    stock_cfg = SimpleNamespace(enabled=True, error_budget=1, history_backfill_days=30)
    monkeypatch.setattr("scraper.config.get_settings", lambda: _fake_settings(stock_cfg))
    monkeypatch.setattr(
        "scraper.moex_stocks.MoexStockClient",
        lambda *a, **k: _FakePipelineClient(stocks=[], raise_fetch=True),
    )
    first = _run(pipeline.run_once_moex_stocks())
    assert first["fetch_failed"] == 1
    assert pipeline._stock_consecutive_failures == 1
    second = _run(pipeline.run_once_moex_stocks())
    assert second["fetch_failed"] == 1
    assert pipeline._stock_consecutive_failures == 2


def test_pipeline_success_upserts_and_resets_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from scraper import pipeline

    stock_cfg = SimpleNamespace(enabled=True, error_budget=1, history_backfill_days=30)
    monkeypatch.setattr("scraper.config.get_settings", lambda: _fake_settings(stock_cfg))
    monkeypatch.setattr(
        "scraper.moex_stocks.MoexStockClient",
        lambda *a, **k: _FakePipelineClient(stocks=[_stock_model("MOEX_SBER")]),
    )
    pipeline._stock_consecutive_failures = 5
    summary = _run(pipeline.run_once_moex_stocks())
    assert summary["stocks_saved"] == 1
    assert summary["history_rows"] == 0
    assert pipeline._stock_consecutive_failures == 0


def test_pipeline_trims_history_to_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC
    from datetime import datetime as _dt
    from types import SimpleNamespace

    from scraper import pipeline
    from scraper.models import StockHistory

    stock_cfg = SimpleNamespace(enabled=True, error_budget=1, history_backfill_days=30)
    monkeypatch.setattr("scraper.config.get_settings", lambda: _fake_settings(stock_cfg))
    old_row = StockHistory(
        internal_id="MOEX_SBER",
        date=_dt(2020, 1, 1).date(),
        close_price=Decimal("10"),
        status="active",
    )
    fresh_row = StockHistory(
        internal_id="MOEX_SBER",
        date=_dt.now(UTC).date(),
        close_price=Decimal("100"),
        status="active",
    )
    monkeypatch.setattr(
        "scraper.moex_stocks.MoexStockClient",
        lambda *a, **k: _FakePipelineClient(
            stocks=[_stock_model("MOEX_SBER")],
            history=[old_row, fresh_row],
        ),
    )
    summary = _run(pipeline.run_once_moex_stocks())
    assert summary["stocks_saved"] == 1
    assert summary["history_rows"] == 1
    assert summary["history_err"] == 0
