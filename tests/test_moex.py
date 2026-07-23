"""Tests for the public MOEX ISS data source client."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scraper.moex import MoexClient, _norm_currency


def test_norm_currency_aliases() -> None:
    assert _norm_currency("SUR") == "RUB"
    assert _norm_currency("sur") == "RUB"
    assert _norm_currency("USD") == "USD"
    assert _norm_currency("EUR") == "EUR"
    assert _norm_currency("unknown") == "RUB"


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, url: str):  # noqa: ANN001 - test double
        return _FakeResp(self._payload)


_PAYLOAD = {
    "securities": {
        "columns": [
            "SECID", "SECNAME", "ISSUER", "SHORTNAME",
            "FACEUNIT", "FACEVALUE", "COUPONVALUE", "COUPONPERIOD",
            "MATDATE", "ISIN",
        ],
        "data": [
            ["TEST1", "Test Bond 1", "OOO Test", "TEST1",
             "SUR", "1000", "90", "2", "2029-01-01", "RU000TEST1"],
            ["TEST2", "Test Eurobond", "Republic", "TEST2",
             "USD", "1000", "50", "2", "2030-05-15", "XS000TEST2"],
        ],
    },
    "marketdata": {
        "columns": ["SECID", "LAST", "YIELD"],
        "data": [["TEST1", "101.5", "11.2"], ["TEST2", "99.0", "5.1"]],
    },
}


@pytest.mark.asyncio
async def test_fetch_bonds_parses_and_normalizes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def _fake_get(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        return _FakeResp(_PAYLOAD)

    monkeypatch.setenv("MOEX_BOARDS", "TQCB")
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _FakeClient(_PAYLOAD))

    client = MoexClient()
    bonds = await client.fetch_bonds()
    assert len(bonds) == 2
    rub = next(b for b in bonds if b.internal_id == "MOEX_TEST1")
    usd = next(b for b in bonds if b.internal_id == "MOEX_TEST2")
    assert rub.currency == "RUB"
    assert rub.price == 101.5
    assert rub.yield_to_maturity == __import__("decimal").Decimal("11.2")
    assert rub.coupon_frequency == 2
    assert rub.maturity_date is not None
    assert usd.currency == "USD"
    assert usd.isin == "XS000TEST2"
    assert rub.fetched_at is not None


_HISTORY_PAYLOAD = {
    "history": {
        "columns": [
            "BOARDID", "TRADEDATE", "SECID", "CLOSE", "YIELDCLOSE",
        ],
        "data": [
            ["TQOB", "2025-01-21", "TEST2", "84.6", "5.10"],
            ["TQOB", "2025-01-22", "TEST2", "85.1", "5.05"],
        ],
    },
    "history.cursor": {"columns": ["INDEX", "TOTAL", "PAGESIZE"], "data": [[0, 2, 100]]},
}

_BONDIZATION_PAYLOAD = {
    "coupons": {
        "columns": ["isin", "name", "coupondate", "value"],
        "data": [
            ["XS000TEST2", "Test Eurobond", "2025-06-29", "38.57"],
            ["XS000TEST2", "Test Eurobond", "2025-12-29", "38.23"],
        ],
    },
    "amortizations": {"columns": [], "data": []},
    "offers": {"columns": [], "data": []},
}


@pytest.mark.asyncio
async def test_fetch_history_parses(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MOEX_BOARDS", "TQOB")
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _FakeClient(_HISTORY_PAYLOAD))
    client = MoexClient()
    client._id_by_internal["MOEX_TEST2"] = "TEST2"
    hist = await client.fetch_history("MOEX_TEST2", _days=30)
    assert len(hist) == 2
    assert hist[0].date is not None
    assert hist[0].price == __import__("decimal").Decimal("84.6")
    assert hist[0].yield_ == __import__("decimal").Decimal("5.10")


@pytest.mark.asyncio
async def test_fetch_coupons_parses(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MOEX_BOARDS", "TQOB")
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _FakeClient(_BONDIZATION_PAYLOAD))
    client = MoexClient()
    client._id_by_internal["MOEX_TEST2"] = "TEST2"
    coupons = await client.fetch_coupons("MOEX_TEST2")
    assert len(coupons) == 2
    assert coupons[0]["date"] is not None
    assert coupons[0]["coupon"] == __import__("decimal").Decimal("38.57")


@pytest.mark.asyncio
async def test_fetch_bonds_currency_filter(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MOEX_BOARDS", "TQOB")
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _FakeClient(_PAYLOAD))
    client = MoexClient()
    usd = await client.fetch_bonds("USD")
    assert len(usd) == 1
    assert usd[0].currency == "USD"


def test_build_coupon_schedule_groups_by_year() -> None:  # type: ignore[no-untyped-def]
    from scraper.pipeline import _build_coupon_schedule

    coupons = [
        {"date": datetime(2025, 6, 29).date(), "coupon": __import__("decimal").Decimal("38.57")},
        {"date": datetime(2025, 12, 29).date(), "coupon": __import__("decimal").Decimal("38.23")},
        {"date": datetime(2026, 6, 29).date(), "coupon": __import__("decimal").Decimal("38.01")},
    ]
    sched = _build_coupon_schedule(coupons)
    assert set(sched.keys()) == {"2025", "2026"}
    assert sched["2025"] == ["2025-06-29", "2025-12-29"]
    assert sched["2026"] == ["2026-06-29"]
