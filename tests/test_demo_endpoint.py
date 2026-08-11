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
