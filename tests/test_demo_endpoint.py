"""Tests for the demo blueprint — live read-only responses."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _enable_demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_DISABLE_SIDE_EFFECTS", "1")
    monkeypatch.delenv("AIGENIS_ENV", raising=False)


async def _seed_bcse_bond(*, internal_id: str = "bcse-live-1", **overrides) -> None:
    from scraper.db import session_scope
    from scraper.orm import BondORM

    fields = {
        "internal_id": internal_id,
        "isin": f"BY0000{internal_id.upper()}",
        "name": "Минфин РБ 2030",
        "issuer": "Министерство финансов Республики Беларусь",
        "currency": "BYN",
        "nominal": Decimal("100"),
        "coupon_rate": Decimal("12.5"),
        "coupon_frequency": 2,
        "maturity_date": date(2030, 8, 7),
        "price": Decimal("98.5"),
        "yield_to_maturity": None,
        "market": "bcse",
        "status": "active",
        "is_government": True,
    }
    fields.update(overrides)
    async with session_scope() as session:
        existing = await session.get(BondORM, fields["internal_id"])
        if existing is None:
            session.add(BondORM(**fields))


def _find(bonds: list, internal_id: str) -> dict:
    return next(b for b in bonds if b["internal_id"] == internal_id)


def _run(coro_fn, **kwargs) -> None:
    async def wrapper():
        await coro_fn(**kwargs)

    asyncio.run(wrapper())


def test_market_data_computes_ytm_duration_score() -> None:
    _run(_seed_bcse_bond, internal_id="bcse-compute")
    resp = client.get("/api/v1/demo/market-data?market=bcse&limit=50")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 1
    bond = _find(body["bonds"], "bcse-compute")
    # YTM derived from price 98.5 / coupon 12.5 / maturity 2030 -> ~12.9%.
    assert bond["yield_to_maturity"] is not None
    assert bond["yield_to_maturity"] > 12.0
    assert bond["computed_ytm"] is True
    # Macaulay duration from real cash flows (positive, less than years to maturity).
    assert bond["duration_years"] is not None
    assert 0 < bond["duration_years"] < (date(2030, 8, 7) - date.today()).days / 365.25
    # Score from the production engine, with a tier and status the UI can render.
    assert bond["score"] is not None
    assert bond["tier"] in {"S", "A", "B", "C", "D"}
    assert bond["score_status"] in {"attractive", "neutral", "review", "high_risk"}
    assert "breakdown" in bond
    assert bond["issuer_risk"]["level"] == "Очень низкий"
    assert bond["issuer_risk"]["score"] >= 90
    # Plain-language explanation (pros / cons / verdict) is always served for scored bonds.
    assert bond["explanation"] is not None
    assert {"verdict", "summary", "strengths", "weaknesses", "factors"} <= set(
        bond["explanation"].keys()
    )
    assert isinstance(bond["explanation"]["strengths"], list)
    assert isinstance(bond["explanation"]["weaknesses"], list)
    assert isinstance(bond["explanation"]["factors"], list)
    assert bond["explanation"]["verdict"] != ""


def test_market_data_explanation_only_with_score() -> None:
    _run(_seed_bcse_bond, internal_id="bcse-noanchor", price=None, yield_to_maturity=None)
    resp = client.get("/api/v1/demo/market-data?market=bcse&limit=50")
    bond = _find(resp.json()["bonds"], "bcse-noanchor")
    assert bond["score"] is None
    assert bond["explanation"] is None


def test_market_data_uses_source_ytm_when_present() -> None:
    _run(
        _seed_bcse_bond,
        internal_id="bcse-source-ytm",
        price=None,
        yield_to_maturity=Decimal("4.0002"),
    )
    resp = client.get("/api/v1/demo/market-data?market=bcse&limit=50")
    bond = _find(resp.json()["bonds"], "bcse-source-ytm")
    assert bond["yield_to_maturity"] == 4.0002
    assert bond["computed_ytm"] is False
    assert bond["score"] is not None


def test_market_data_no_anchor_means_no_data() -> None:
    _run(_seed_bcse_bond, internal_id="bcse-noanchor", price=None, yield_to_maturity=None)
    resp = client.get("/api/v1/demo/market-data?market=bcse&limit=50")
    bond = _find(resp.json()["bonds"], "bcse-noanchor")
    assert bond["yield_to_maturity"] is None
    assert bond["score"] is None
    assert bond["score_status"] is None


def test_market_data_invalid_math_returns_none() -> None:
    _run(_seed_bcse_bond, internal_id="bcse-badprice", price=Decimal("0"))
    resp = client.get("/api/v1/demo/market-data?market=bcse&limit=50")
    bond = _find(resp.json()["bonds"], "bcse-badprice")
    assert bond["yield_to_maturity"] is None
    assert bond["score"] is None


def test_search_returns_matches_with_explanation() -> None:
    _run(_seed_bcse_bond, internal_id="bcse-search-1", name="Газпром 2027")
    _run(_seed_bcse_bond, internal_id="bcse-search-2", name="Минфин 2030")
    resp = client.get("/api/v1/demo/search?q=Газпром&limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "Газпром"
    ids = [b["internal_id"] for b in body["bonds"]]
    assert "bcse-search-1" in ids
    assert "bcse-search-2" not in ids
    match = next(b for b in body["bonds"] if b["internal_id"] == "bcse-search-1")
    assert match["explanation"] is not None
    assert match["score"] is not None


def test_search_by_isin_and_internal_id() -> None:
    _run(_seed_bcse_bond, internal_id="bcse-isin", isin="BY0000ISIN01")
    resp = client.get("/api/v1/demo/search?q=ISIN01")
    ids = [b["internal_id"] for b in resp.json()["bonds"]]
    assert "bcse-isin" in ids

    resp = client.get("/api/v1/demo/search?q=bcse-isin")
    ids = [b["internal_id"] for b in resp.json()["bonds"]]
    assert "bcse-isin" in ids


def test_search_empty_query_returns_empty() -> None:
    resp = client.get("/api/v1/demo/search?q=")
    assert resp.status_code == 422


def test_search_market_filter() -> None:
    _run(_seed_bcse_bond, internal_id="bcse-mkt-filter", market="bcse")
    resp = client.get("/api/v1/demo/search?q=Минфин&market=moex")
    ids = [b["internal_id"] for b in resp.json()["bonds"]]
    assert "bcse-mkt-filter" not in ids


def test_bond_detail_returns_history_and_schedule() -> None:
    _run(_seed_bcse_bond, internal_id="bcse-detail-1")
    resp = client.get("/api/v1/demo/bond/bcse-detail-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["internal_id"] == "bcse-detail-1"
    assert body["explanation"] is not None
    assert "history" in body
    assert isinstance(body["history"], list)
    assert "coupon_schedule" in body


def test_bond_detail_unknown_id_404() -> None:
    resp = client.get("/api/v1/demo/bond/no-such-bond-123")
    assert resp.status_code == 404


def test_portfolio_impact_deterministic() -> None:
    resp = client.post(
        "/api/v1/demo/portfolio-impact",
        json={"bond_id": "demo-bond-001", "allocation_pct": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["bond_id"] == "demo-bond-001"
    assert body["allocation_pct"] == 10
    assert body["fixtures_version"] == "v1"
    assert "expected_yield_pct" in body["before"]
    assert "expected_yield_pct" in body["after"]
    assert body["delta_expected_yield_bps"] > 0
    assert body["risk_profile_fit"] in {"ok", "borderline", "off"}


def test_portfolio_impact_unknown_bond_404() -> None:
    resp = client.post(
        "/api/v1/demo/portfolio-impact",
        json={"bond_id": "demo-bond-XXX", "allocation_pct": 5},
    )
    assert resp.status_code == 404


def test_portfolio_impact_invalid_allocation_422() -> None:
    resp = client.post(
        "/api/v1/demo/portfolio-impact",
        json={"bond_id": "demo-bond-001", "allocation_pct": 50},
    )
    assert resp.status_code == 422


def test_portfolio_impact_blocks_in_production() -> None:
    import os

    os.environ["AIGENIS_ENV"] = "production"
    os.environ.pop("DEMO_DISABLE_SIDE_EFFECTS", None)
    try:
        resp = client.post(
            "/api/v1/demo/portfolio-impact",
            json={"bond_id": "demo-bond-001", "allocation_pct": 5},
        )
        assert resp.status_code == 403
    finally:
        os.environ.pop("AIGENIS_ENV", None)
        os.environ["DEMO_DISABLE_SIDE_EFFECTS"] = "1"


def test_demo_desk_curve_endpoint() -> None:
    resp = client.get("/api/v1/demo/desk/curve?currency=BYN&market=bcse")
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "BYN"
    assert "points" in body
    assert "slope" in body


def test_demo_desk_rv_endpoint() -> None:
    resp = client.get("/api/v1/demo/desk/rv?currency=BYN&market=bcse")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


def test_demo_desk_stress_endpoint() -> None:
    resp = client.post(
        "/api/v1/demo/desk/stress",
        json={
            "scenario": "parallel_+100bp",
            "market": "BCSE",
            "capital": 50000.0,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "scenario" in body
    assert "pnl_amount" in body
    assert "pnl_pct" in body
    assert "by_position" in body
    assert "positions" in body


def test_demo_portfolio_optimize_endpoint() -> None:
    resp = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={
            "capital": 50000.0,
            "strategy": "Balanced",
            "currency": "BYN",
            "top_n": 5,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "metrics" in body
    assert "expected_return" in body["metrics"]
    assert "allocations" in body
    assert "order_tickets" in body


def test_demo_search_special_characters_and_sql_injection() -> None:
    # Regex characters, SQL injection string, unicode, emojis
    for query in ["Газпром", ".*+?^${}()|[]\\", "' OR 1=1 --", "🚀💎", "   "]:
        resp = client.get(f"/api/v1/demo/search?q={query}")
        assert resp.status_code == 200
        body = resp.json()
        assert "bonds" in body
        assert isinstance(body["bonds"], list)


def test_demo_desk_curve_exotic_currency_and_market() -> None:
    for cur in ["USD", "EUR", "RUB", "CNY", "XYZ"]:
        resp = client.get(f"/api/v1/demo/desk/curve?currency={cur}&market=unknown_market")
        assert resp.status_code == 200
        body = resp.json()
        assert "points" in body
        assert "slope" in body


def test_demo_desk_stress_boundary_capitals() -> None:
    for cap in [0.0, 100.0, 1_000_000_000.0]:
        resp = client.post(
            "/api/v1/demo/desk/stress",
            json={
                "scenario": "parallel_+100bp",
                "market": "BCSE",
                "capital": cap,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "pnl_amount" in body
        assert "positions" in body


def test_demo_portfolio_optimize_unknown_strategy() -> None:
    resp = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={
            "capital": 50000.0,
            "strategy": "HyperGrowthNonExistent",
            "currency": "BYN",
            "top_n": 10,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "metrics" in body
    assert "allocations" in body


def test_demo_portfolio_optimize_small_capital_and_budget_constraints() -> None:
    # Test very small capital (e.g. 4 BYN / 4 USD)
    resp_tiny = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={
            "capital": 4.0,
            "strategy": "Carry Trade",
            "currency": "USD",
            "top_n": 8,
        },
    )
    assert resp_tiny.status_code == 200
    body_tiny = resp_tiny.json()
    assert "allocations" in body_tiny
    assert "order_tickets" in body_tiny
    # When capital is too small for 1 lot, it should not buy $15,000 worth of bonds!
    total_spent_tiny = sum(item["amount"] for item in body_tiny["allocations"])
    assert total_spent_tiny <= 4.0 or len(body_tiny["allocations"]) == 0

    # Test medium capital (e.g. 4,000 USD)
    resp_med = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={
            "capital": 4000.0,
            "strategy": "Carry Trade",
            "currency": "USD",
            "top_n": 8,
        },
    )
    assert resp_med.status_code == 200
    body_med = resp_med.json()
    assert "allocations" in body_med
    if body_med["allocations"]:
        total_spent_med = sum(item["amount"] for item in body_med["allocations"])
        assert total_spent_med <= 4000.0
        # Check weights sum approximately to 100%
        total_weight = sum(item["weight_pct"] for item in body_med["allocations"])
        assert 98.0 <= total_weight <= 102.0


def test_demo_portfolio_optimize_carry_trade_all_currencies() -> None:
    for cur in ["BYN", "USD", "RUB"]:
        resp = client.post(
            "/api/v1/demo/portfolio/optimize",
            json={
                "capital": 25000.0,
                "strategy": "Carry Trade",
                "currency": cur,
                "top_n": 6,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["strategy"] == "Carry Trade"
        if body["allocations"]:
            total_spent = sum(item["amount"] for item in body["allocations"])
            assert total_spent <= 25000.0


def test_demo_portfolio_optimize_market_isolation_bcse_and_moex() -> None:
    # 1. BCSE Dollarization: only BCSE / Belarusian bonds, no MOEX bonds
    resp_bcse_usd = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={
            "capital": 50000.0,
            "strategy": "Dollarization",
            "currency": "BYN",
            "market": "bcse",
            "top_n": 8,
        },
    )
    assert resp_bcse_usd.status_code == 200
    body_bcse = resp_bcse_usd.json()
    for alloc in body_bcse.get("allocations", []):
        assert "moex" not in alloc["internal_id"].lower()

    # 2. BCSE Metals++: only authentic Aigenis metal bonds
    resp_bcse_metals = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={
            "capital": 50000.0,
            "strategy": "Metals++",
            "currency": "BYN",
            "market": "bcse",
            "top_n": 8,
        },
    )
    assert resp_bcse_metals.status_code == 200
    body_metals = resp_bcse_metals.json()
    for alloc in body_metals.get("allocations", []):
        assert "moex" not in alloc["internal_id"].lower()
        assert "южурал" not in alloc["name"].lower()
        assert "селигдар" not in alloc["name"].lower()




