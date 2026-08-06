"""HTTP + service tests for the stocks API, freshness, alerts and instruments."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.auth.service import create_access_token
from api.main import app
from scraper.db import dispose, session_scope
from scraper.models import InstrumentRef, bond_instrument_ref, stock_instrument_ref
from scraper.orm import BondORM, StockHistoryORM, StockORM, UserORM

client = TestClient(app)

NOW = datetime.now(UTC)


@pytest.fixture(autouse=True)
def _clean_db():
    yield

    async def _drop():
        await dispose()

    asyncio.run(_drop())


def _run(coro):
    return asyncio.run(coro)


def _seed_stocks(rows: list[StockORM]) -> None:
    async def go() -> None:
        async with session_scope() as s:
            for r in rows:
                s.add(r)

    _run(go())


def _seed_history(rows: list[StockHistoryORM]) -> None:
    async def go() -> None:
        async with session_scope() as s:
            for r in rows:
                s.add(r)

    _run(go())


def _seed_user(user_id: int = 1, tier: str = "pro") -> None:
    async def go() -> None:
        async with session_scope() as s:
            s.add(
                UserORM(
                    id=user_id,
                    email=f"u{user_id}@t.co",
                    name="U",
                    password_hash="x",
                    role="user",
                    subscription_tier=tier,
                    subscription_expires_at=NOW + timedelta(days=30),
                    is_active=True,
                )
            )

    _run(go())


def _auth(user_id: int = 1) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def _stock(
    iid: str,
    board: str = "TQBR",
    price: Decimal | None = Decimal("100.00"),
    value: Decimal | None = Decimal("1000"),
    fetched_at: datetime | None = NOW,
    status: str = "active",
    sector: str = "Банки",
    dividend_yield: Decimal | None = Decimal("8.2"),
) -> StockORM:
    return StockORM(
        internal_id=iid,
        secid=iid.removeprefix("MOEX_"),
        name=f"Stock {iid}",
        board=board,
        currency="RUB",
        price=price,
        value_traded=value,
        pe_ratio=Decimal("6.5"),
        pbr_ratio=Decimal("0.8"),
        dividend_yield=dividend_yield,
        sector=sector,
        status=status,
        fetched_at=fetched_at or NOW,
    )


def test_list_stocks_no_score_field() -> None:
    _seed_stocks([_stock("MOEX_SBER"), _stock("MOEX_GAZP", value=Decimal("9999"))])
    resp = client.get("/api/v1/stocks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["internal_id"] == "MOEX_GAZP"
    assert all("score" not in row for row in data)
    assert data[0]["currency"] == "RUB"
    assert data[0]["pe_ratio"] == 6.5


def test_stock_detail_has_no_score() -> None:
    _seed_stocks([_stock("MOEX_SBER")])
    resp = client.get("/api/v1/stocks/MOEX_SBER")
    assert resp.status_code == 200
    body = resp.json()
    assert body["secid"] == "SBER"
    assert "score" not in body
    assert client.get("/api/v1/stocks/MOEX_NOPE").status_code == 404


def test_stocks_filters_and_pagination() -> None:
    _seed_stocks(
        [
            _stock("MOEX_SBER"),
            _stock("MOEX_SBER2", board="TQOD", price=Decimal("2.98")),
            _stock("MOEX_GAZP", sector="Нефть и газ"),
        ]
    )
    resp = client.get("/api/v1/stocks", params={"board": "TQOD"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    resp = client.get("/api/v1/stocks", params={"sector": "Банки"})
    assert {r["internal_id"] for r in resp.json()} == {"MOEX_SBER", "MOEX_SBER2"}
    resp = client.get("/api/v1/stocks", params={"sort_by": "bogus", "limit": 1})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_stats_and_sectors() -> None:
    _seed_stocks(
        [
            _stock("MOEX_SBER"),
            _stock("MOEX_SBER2", board="TQOD"),
            _stock("MOEX_GAZP", sector="Нефть и газ", status="suspended"),
        ]
    )
    stats = client.get("/api/v1/stocks/stats").json()
    assert stats["total_stocks"] == 3
    assert stats["active_stocks"] == 2
    assert stats["by_board"] == {"TQBR": 2, "TQOD": 1}
    sectors = client.get("/api/v1/stocks/sectors").json()
    by_name = {s["sector"]: s for s in sectors}
    assert by_name["Банки"]["count"] == 2
    assert by_name["Банки"]["avg_pe"] == 6.5


def test_board_and_search() -> None:
    _seed_stocks([_stock("MOEX_SBER"), _stock("MOEX_GAZP", board="TQOD")])
    resp = client.get("/api/v1/stocks/board/tqbr")
    assert resp.status_code == 200
    assert [r["internal_id"] for r in resp.json()] == ["MOEX_SBER"]
    found = client.get("/api/v1/stocks/search/GAZ").json()
    assert found[0]["internal_id"] == "MOEX_GAZP"


def test_stock_history_endpoint() -> None:
    _seed_stocks([_stock("MOEX_SBER")])
    _seed_history(
        [
            StockHistoryORM(
                internal_id="MOEX_SBER",
                date=date(2026, 8, 5),
                close_price=Decimal("255.90"),
                volume=38123000,
            ),
            StockHistoryORM(
                internal_id="MOEX_SBER",
                date=date(2026, 8, 4),
                close_price=Decimal("255.10"),
            ),
        ]
    )
    rows = client.get("/api/v1/stocks/MOEX_SBER/history", params={"days": 30}).json()
    assert [r["date"] for r in rows] == ["2026-08-04", "2026-08-05"]
    assert rows[1]["volume"] == 38123000
    assert client.get("/api/v1/stocks/MOEX_GAZP/history").status_code == 404


def test_freshness_statuses() -> None:
    _seed_stocks(
        [
            _stock("MOEX_SBER", fetched_at=NOW - timedelta(hours=1)),
            _stock("MOEX_GAZP", fetched_at=NOW - timedelta(hours=1)),
            _stock("MOEX_LKOH", board="TQOD", fetched_at=NOW - timedelta(hours=10)),
            _stock("MOEX_YNDX", board="TQDE", fetched_at=NOW - timedelta(hours=48)),
        ]
    )
    resp = client.get("/api/v1/stocks/freshness")
    assert resp.status_code == 200
    by_board = {r["board"]: r for r in resp.json()}
    assert by_board["TQBR"]["status"] == "ok"
    assert by_board["TQBR"]["instruments"] == 2
    assert by_board["TQOD"]["status"] == "stale"
    assert by_board["TQDE"]["status"] == "critical"
    assert by_board["TQDE"]["last_ingest"] is not None


def test_freshness_old_board_is_critical() -> None:
    _seed_stocks([_stock("MOEX_SBER", fetched_at=NOW - timedelta(hours=500))])
    rows = client.get("/api/v1/stocks/freshness").json()
    assert rows[0]["status"] == "critical"


def test_top_stocks_available() -> None:
    _seed_stocks([_stock("MOEX_SBER"), _stock("MOEX_GAZP", dividend_yield=Decimal("3.0"))])
    resp = client.get("/api/v1/stocks/top/dividend")
    assert resp.status_code == 200
    assert resp.json()[0]["internal_id"] == "MOEX_SBER"
    caps = client.get("/api/v1/stocks/top/cap")
    assert caps.status_code == 200


def test_alert_rule_metric_per_asset_class() -> None:
    _seed_user()
    _seed_stocks([_stock("MOEX_SBER")])

    async def seed_bond() -> None:
        async with session_scope() as s:
            s.add(
                BondORM(
                    internal_id="BYN123",
                    name="Test Bond",
                    currency="BYN",
                    status="active",
                    fetched_at=NOW,
                )
            )

    _run(seed_bond())
    headers = _auth()
    stock_ok = client.post(
        "/api/v1/alerts/rules",
        headers=headers,
        json={
            "internal_id": "MOEX_SBER",
            "metric": "pbr",
            "direction": "below",
            "threshold": 1.0,
        },
    )
    assert stock_ok.status_code == 200
    assert stock_ok.json()["metric"] == "pbr"
    bad_stock_metric = client.post(
        "/api/v1/alerts/rules",
        headers=headers,
        json={
            "internal_id": "MOEX_SBER",
            "metric": "ytm",
            "direction": "below",
            "threshold": 5.0,
        },
    )
    assert bad_stock_metric.status_code == 400
    bad_bond_metric = client.post(
        "/api/v1/alerts/rules",
        headers=headers,
        json={
            "internal_id": "BYN123",
            "metric": "pe",
            "direction": "above",
            "threshold": 10.0,
        },
    )
    assert bad_bond_metric.status_code == 400
    bond_ok = client.post(
        "/api/v1/alerts/rules",
        headers=headers,
        json={
            "internal_id": "BYN123",
            "metric": "ytm",
            "direction": "above",
            "threshold": 8.0,
        },
    )
    assert bond_ok.status_code == 200
    missing = client.post(
        "/api/v1/alerts/rules",
        headers=headers,
        json={
            "internal_id": "MOEX_NOPE",
            "metric": "price",
            "direction": "below",
            "threshold": 1.0,
        },
    )
    assert missing.status_code == 404


def test_alert_service_current_value_stock_metrics() -> None:
    from notifications.alerts_service import _build_message, _current_value

    stock = _stock("MOEX_SBER", price=Decimal("100"))
    assert _current_value(stock, "price") == Decimal("100")
    assert _current_value(stock, "pbr") == Decimal("0.8")
    assert _current_value(stock, "pe") == Decimal("6.5")
    assert _current_value(stock, "dividend_yield") == Decimal("8.2")
    assert _current_value(stock, "ytm") is None
    rule = type(
        "Rule",
        (),
        {"internal_id": "MOEX_SBER", "metric": "pbr", "direction": "below", "threshold": 1.0},
    )
    msg = _build_message(rule, Decimal("0.7"))
    assert "P/B" in msg
    assert "упал" in msg


def test_instrument_ref_and_summary() -> None:
    from scraper.repositories.instruments import instrument_summary, search_instruments

    _seed_stocks([_stock("MOEX_SBER")])

    async def seed_bond() -> None:
        async with session_scope() as s:
            s.add(
                BondORM(
                    internal_id="BYN123",
                    name="Test Bond",
                    currency="BYN",
                    yield_to_maturity=Decimal("9.5"),
                    status="active",
                    fetched_at=NOW,
                )
            )

    _run(seed_bond())
    ref = stock_instrument_ref(_stock("MOEX_SBER"))
    assert isinstance(ref, InstrumentRef)
    assert ref.asset_class == "equity"
    assert ref.internal_id == "MOEX_SBER"
    bond_ref = bond_instrument_ref(
        BondORM(
            internal_id="BYN123",
            name="Test Bond",
            currency="BYN",
            status="active",
            fetched_at=NOW,
        )
    )
    assert bond_ref.asset_class == "bond"

    async def go() -> None:
        async with session_scope() as s:
            stock_summary = await instrument_summary(s, "MOEX_SBER")
            bond_summary = await instrument_summary(s, "BYN123")
            stock_hits = await search_instruments(s, "SBER")
            bond_hits = await search_instruments(s, "Test")
            return stock_summary, bond_summary, stock_hits, bond_hits

    stock_summary, bond_summary, stock_hits, bond_hits = _run(go())
    assert stock_summary is not None and stock_summary.asset_class == "equity"
    assert bond_summary is not None and bond_summary.asset_class == "bond"
    assert bond_summary.headline is not None and "Доходность" in bond_summary.headline
    assert {h.asset_class for h in stock_hits} == {"equity"}
    assert {h.asset_class for h in bond_hits} == {"bond"}

    async def go_none() -> None:
        async with session_scope() as s:
            return await instrument_summary(s, "MOEX_NOPE")

    assert _run(go_none()) is None
