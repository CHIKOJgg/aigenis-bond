"""Tests for the public MOEX ISS data source client."""

from __future__ import annotations

from datetime import datetime

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

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, url: str):
        return _FakeResp(self._payload)


_PAYLOAD = {
    "securities": {
        "columns": [
            "SECID",
            "SECNAME",
            "ISSUER",
            "SHORTNAME",
            "FACEUNIT",
            "FACEVALUE",
            "COUPONVALUE",
            "COUPONPERIOD",
            "MATDATE",
            "ISIN",
        ],
        "data": [
            [
                "TEST1",
                "Test Bond 1",
                "OOO Test",
                "TEST1",
                "SUR",
                "1000",
                "90",
                "182",
                "2029-01-01",
                "RU000TEST1",
            ],
            [
                "TEST2",
                "Test Eurobond",
                "Republic",
                "TEST2",
                "USD",
                "1000",
                "50",
                "182",
                "2030-05-15",
                "XS000TEST2",
            ],
        ],
    },
    "marketdata": {
        "columns": ["SECID", "LAST", "YIELD"],
        "data": [["TEST1", "101.5", "11.2"], ["TEST2", "99.0", "5.1"]],
    },
}


@pytest.mark.asyncio
async def test_fetch_bonds_parses_and_normalizes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def _fake_get(*args, **kwargs):
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
            "BOARDID",
            "TRADEDATE",
            "SECID",
            "CLOSE",
            "YIELDCLOSE",
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


@pytest.mark.asyncio
async def test_fetch_bonds_skips_parse_failure(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "securities": {
            "columns": [
                "SECID",
                "SECNAME",
                "ISSUER",
                "SHORTNAME",
                "FACEUNIT",
                "FACEVALUE",
                "COUPONVALUE",
                "COUPONPERIOD",
                "MATDATE",
                "ISIN",
                "COUPONPERCENT",
            ],
            "data": [
                [
                    "BAD1",
                    "Bad bond",
                    "OOO Test",
                    "BAD1",
                    "SUR",
                    "NaN",
                    "90",
                    "182",
                    "2029-01-01",
                    "RU000BAD1",
                    "10",
                ],
                [
                    "GOOD1",
                    "Good bond",
                    "OOO Test",
                    "GOOD1",
                    "SUR",
                    "1000",
                    "90",
                    "182",
                    "2029-01-01",
                    "RU000GOOD1",
                    "10",
                ],
            ],
        },
        "marketdata": {
            "columns": ["SECID", "LAST", "YIELD"],
            "data": [["BAD1", "101.5", "11.2"], ["GOOD1", "101.5", "11.2"]],
        },
    }

    monkeypatch.setenv("MOEX_BOARDS", "TQCB")
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _FakeClient(payload))
    bonds = await MoexClient().fetch_bonds()
    assert [b.internal_id for b in bonds] == ["MOEX_GOOD1"]


@pytest.mark.asyncio
async def test_fetch_history_skips_bad_candle(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "history": {
            "columns": ["BOARDID", "TRADEDATE", "SECID", "CLOSE", "YIELDCLOSE"],
            "data": [
                ["TQOB", "2025-01-21", "TEST2", "NaN", "5.10"],
                ["TQOB", "2025-01-22", "TEST2", "85.1", "5.05"],
            ],
        },
        "history.cursor": {"columns": ["INDEX", "TOTAL", "PAGESIZE"], "data": [[0, 2, 100]]},
    }

    monkeypatch.setenv("MOEX_BOARDS", "TQOB")
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _FakeClient(payload))
    client = MoexClient()
    client._id_by_internal["MOEX_TEST2"] = "TEST2"
    hist = await client.fetch_history("MOEX_TEST2", _days=30)
    assert len(hist) == 1
    assert hist[0].price == __import__("decimal").Decimal("85.1")


def test_boards_env(monkeypatch) -> None:
    from scraper.moex import _boards

    monkeypatch.setenv("MOEX_BOARDS", "tqcb, tqob, ")
    assert _boards() == ["TQCB", "TQOB"]
    monkeypatch.delenv("MOEX_BOARDS")
    assert _boards() == ["TQCB", "TQOB"]


def test_freq_from_coupon_period() -> None:
    from scraper.moex import _freq_from_coupon_period

    assert _freq_from_coupon_period(12) == 12
    assert _freq_from_coupon_period(365) == 1
    assert _freq_from_coupon_period(91) == 4
    assert _freq_from_coupon_period(30) == 12
    assert _freq_from_coupon_period(50) is None
    assert _freq_from_coupon_period("abc") is None


def test_moex_status() -> None:
    from scraper.moex import _moex_status

    assert _moex_status({"BOARDID": "TQCB"}, {"LCLOSE": "100"}) == "active"
    assert _moex_status({"BOARDID": "TQCB"}, {"LAST": "100"}) == "active"
    assert _moex_status({"BOARDID": "TQCB"}, None) == "active"
    assert _moex_status({"BOARDID": "SMTH"}, {}) == "unknown"


def test_to_dec_invalid() -> None:
    from scraper.moex import _to_dec

    assert _to_dec("abc") is None


def test_coupon_rate_pct_branches() -> None:
    from scraper.moex import _coupon_rate_pct

    assert _coupon_rate_pct({"COUPONPERCENT": "10"}) == __import__("decimal").Decimal("10")
    assert (
        _coupon_rate_pct({"COUPONVALUE": None, "FACEVALUE": "1000", "COUPONPERIOD": "182"}) is None
    )
    assert (
        _coupon_rate_pct({"COUPONVALUE": "50", "FACEVALUE": "1000", "COUPONPERIOD": "abc"}) is None
    )
    assert _coupon_rate_pct({"COUPONVALUE": "50", "FACEVALUE": "1000", "COUPONPERIOD": "0"}) is None
    derived = _coupon_rate_pct({"COUPONVALUE": "50", "FACEVALUE": "1000", "COUPONPERIOD": "182"})
    assert derived is not None
    assert abs(float(derived) - 10.0275) < 0.001


def test_to_date_branches() -> None:
    from datetime import datetime as _dt

    from scraper.moex import _to_date

    assert _to_date("") is None
    assert _to_date(_dt(2024, 5, 1, 12, 30)).isoformat() == "2024-05-01"
    assert _to_date("not-a-date") is None


def test_parse_iss_rows_missing_block() -> None:
    from scraper.moex import _parse_iss_rows

    assert _parse_iss_rows({"other": 1}, "securities") == []


def test_quote_and_yield_branches() -> None:
    from decimal import Decimal

    from scraper.moex import _quote_and_yield

    assert _quote_and_yield({"SECID": "X"}, {"LAST": "0"}) == (None, None)
    sec = {"COUPONPERCENT": "10", "COUPONPERIOD": "182", "MATDATE": "2030-01-01"}
    price, ytm = _quote_and_yield(sec, {"LAST": "100"})
    assert price == Decimal("100")
    assert ytm is not None
    assert Decimal("9") < ytm < Decimal("11")


class _HandlerClient:
    def __init__(self, handler) -> None:
        self._handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def get(self, url: str):
        return self._handler(url)


class _RaisingResp:
    def raise_for_status(self) -> None:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_client_context_and_listing(monkeypatch) -> None:
    async with MoexClient() as client:
        assert client is not None
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _FakeClient(_PAYLOAD))
    rows = await MoexClient().fetch_listing(None)
    assert (
        rows
        == [
            {"internal_id": "MOEX_TEST1", "currency": "RUB", "name": "Test Bond 1"},
            {"internal_id": "MOEX_TEST2", "currency": "USD", "name": "Test Eurobond"},
        ]
        * 2
    )


@pytest.mark.asyncio
async def test_fetch_bonds_board_failure(monkeypatch) -> None:
    def handler(url: str):
        if "/boards/TQCB/" in url:
            raise RuntimeError("board down")
        return _FakeResp(_PAYLOAD)

    monkeypatch.setenv("MOEX_BOARDS", "TQCB,TQOB")
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _HandlerClient(handler))
    bonds = await MoexClient().fetch_bonds()
    assert [b.internal_id for b in bonds] == ["MOEX_TEST1", "MOEX_TEST2"]


@pytest.mark.asyncio
async def test_fetch_bonds_cap_and_skip(monkeypatch) -> None:
    payload = {
        "securities": {
            "columns": ["SECID", "SECNAME", "FACEUNIT"],
            "data": [
                [None, "No id bond", "USD"],
                ["NOTE1", "СФО БКС Структурные Ноты N", "USD"],
                ["OK1", "Ok bond", "USD"],
                ["OK2", "Ok bond 2", "USD"],
            ],
        },
        "marketdata": {"columns": ["SECID"], "data": []},
    }

    monkeypatch.setenv("MOEX_BOARDS", "TQCB")
    monkeypatch.setenv("MOEX_CAP", "1")
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _FakeClient(payload))
    bonds = await MoexClient().fetch_bonds()
    assert len(bonds) == 1


@pytest.mark.asyncio
async def test_fetch_detail_retries_tqob(monkeypatch) -> None:
    def handler(url: str):
        if "/boards/TQCB/" in url:
            return _FakeResp({})
        return _FakeResp(_PAYLOAD)

    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _HandlerClient(handler))
    bond = await MoexClient().fetch_detail("MOEX_TEST1")
    assert bond.internal_id == "MOEX_TEST1"
    assert bond.currency == "RUB"


@pytest.mark.asyncio
async def test_fetch_detail_unknown(monkeypatch) -> None:
    from scraper.errors import NotFoundError

    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _FakeClient(_PAYLOAD))
    with pytest.raises(NotFoundError):
        await MoexClient().fetch_detail("NOT_MOEX_1")


@pytest.mark.asyncio
async def test_fetch_history_unknown_and_board_retry(monkeypatch) -> None:
    def handler(url: str):
        if "/boards/TQCB/" in url:
            raise RuntimeError("board down")
        return _FakeResp(_HISTORY_PAYLOAD)

    monkeypatch.setenv("MOEX_BOARDS", "TQOB")
    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _HandlerClient(handler))
    client = MoexClient()
    assert await client.fetch_history("NOT_MOEX_1") == []
    assert await client.fetch_history("NOT_MOEX_1", _days=1) == []


@pytest.mark.asyncio
async def test_fetch_history_inner_exception(monkeypatch) -> None:
    def handler(url: str):
        raise RuntimeError("down")

    monkeypatch.setattr("httpx.AsyncClient", lambda *a, **k: _HandlerClient(handler))
    client = MoexClient()
    assert await client.fetch_history("MOEX_TEST1") == []


@pytest.mark.asyncio
async def test_fetch_history_client_creation_fails(monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("no client")

    monkeypatch.setattr("httpx.AsyncClient", boom)
    assert await MoexClient().fetch_history("MOEX_TEST1") == []


@pytest.mark.asyncio
async def test_fetch_coupons_unknown_and_failure(monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("no client")

    monkeypatch.setattr("httpx.AsyncClient", boom)
    client = MoexClient()
    assert await client.fetch_coupons("NOT_MOEX_1") == []
    assert await client.fetch_coupons("MOEX_TEST1") == []


def test_quote_and_yield_price_only() -> None:
    from decimal import Decimal

    from scraper.moex import _quote_and_yield

    price, ytm = _quote_and_yield({"SECID": "X"}, {"LAST": "100"})
    assert price == Decimal("100")
    assert ytm is None
