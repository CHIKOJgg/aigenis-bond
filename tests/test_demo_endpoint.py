"""Tests for the demo blueprint — live read-only responses."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _enable_demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_DISABLE_SIDE_EFFECTS", "1")
    monkeypatch.delenv("AIGENIS_ENV", raising=False)


@pytest.fixture(autouse=True)
def _clear_demo_snapshot_cache() -> None:
    """Drop the in-process market/search snapshot cache between tests.

    The cache lives for 300s, so a short test run would otherwise serve a
    stale snapshot (seeded bonds missing) to every test after the first one.
    """
    import api.demo as demo_mod

    demo_mod._market_cache.clear()
    demo_mod._market_inflight.clear()
    yield
    demo_mod._market_cache.clear()
    demo_mod._market_inflight.clear()


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
    ids = [b["internal_id"] for b in resp.json()["bonds"]]
    # Без рыночных якорей (цена/доходность) бумага не проходит в market-data:
    # ни скор, ни объяснение не показываются, потому что нет данных для оценки.
    assert "bcse-noanchor" not in ids


def test_market_data_uses_source_ytm_when_present() -> None:
    _run(
        _seed_bcse_bond,
        internal_id="bcse-source-ytm",
        price=Decimal("98.5"),
        coupon_rate=None,
        yield_to_maturity=Decimal("4.0002"),
    )
    resp = client.get("/api/v1/demo/market-data?market=bcse&limit=50")
    bond = _find(resp.json()["bonds"], "bcse-source-ytm")
    # Без купона ценовой переоценки нет — используется сохранённая (фидовая)
    # доходность, а не вычисленная.
    assert bond["yield_to_maturity"] == 4.0002
    assert bond["computed_ytm"] is False
    assert bond["score"] is not None


def test_market_data_metal_bond_has_no_yield() -> None:
    _run(
        _seed_bcse_bond,
        internal_id="bcse-metal-xau",
        currency="XAU",
        nominal=Decimal("1000"),
        coupon_rate=Decimal("0.001"),
        price=Decimal("1019"),
        yield_to_maturity=Decimal("12.0"),
    )
    resp = client.get("/api/v1/demo/market-data?market=bcse&limit=50")
    bond = _find(resp.json()["bonds"], "bcse-metal-xau")
    # Металлическая бескупонная бумага: доходности нет вовсе — ни хранимой
    # 12%, ни выведенной из цены 1019 (цена = последняя цена сделки).
    assert bond["yield_to_maturity"] is None
    assert bond["computed_ytm"] is False
    assert bond["distressed"] is False
    assert bond["score"] is not None


def test_market_data_no_anchor_means_no_data() -> None:
    _run(_seed_bcse_bond, internal_id="bcse-noanchor", price=None, yield_to_maturity=None)
    resp = client.get("/api/v1/demo/market-data?market=bcse&limit=50")
    ids = [b["internal_id"] for b in resp.json()["bonds"]]
    # Ни цены, ни доходности — бумага исключена из рыночного среза целиком.
    assert "bcse-noanchor" not in ids


def test_market_data_invalid_math_returns_none() -> None:
    _run(_seed_bcse_bond, internal_id="bcse-badprice", price=Decimal("0"))
    resp = client.get("/api/v1/demo/market-data?market=bcse&limit=50")
    ids = [b["internal_id"] for b in resp.json()["bonds"]]
    # Цена 0% от номинала — испорченная котировка вне диапазона 10–150%:
    # из рыночного среза исключается, а не показывается с фиктивным скором.
    assert "bcse-badprice" not in ids


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


def test_search_matches_display_name_alias_for_sovereign_bcse() -> None:
    # BCSE sovereign issues are stored under the generic issuer title while
    # the UI displays "Минфин РБ (выпуск ...)" — search must find them by the
    # displayed name, not only by the raw stored name.
    _run(
        _seed_bcse_bond,
        internal_id="MF-LB-BYN-0400",
        isin="004400",
        name="Министерство финансов Республики Беларусь",
        market="bcse",
    )
    resp = client.get("/api/v1/demo/search?q=минфин&market=bcse")
    assert resp.status_code == 200
    ids = [b["internal_id"] for b in resp.json()["bonds"]]
    assert "MF-LB-BYN-0400" in ids
    resp = client.get("/api/v1/demo/search?q=минфин рб&market=bcse")
    ids = [b["internal_id"] for b in resp.json()["bonds"]]
    assert "MF-LB-BYN-0400" in ids


def test_search_display_name_mirrors_frontend_formatting() -> None:
    import api.demo as demo_mod

    assert (
        demo_mod._search_display_name(
            "Министерство финансов Республики Беларусь", "MF-LB-BYN-0405", "004405"
        )
        == "Минфин РБ (выпуск 0405)"
    )
    assert (
        demo_mod._search_display_name("Министерство финансов Республики Беларусь", "004400", None)
        == "Минфин РБ (выпуск 004400)"
    )
    assert demo_mod._search_display_name("Минфин РБ 2030", "x-1", None) == "Минфин РБ 2030"
    assert demo_mod._search_display_name(None, "MF-LB-BYN-0400", None) == "MF-LB-BYN-0400"


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


def test_demo_portfolio_optimize_full_path_buys_lots_in_currency() -> None:
    # Раньше оптимизатор в тестах всегда возвращался на "нет ликвидных бумаг":
    # ни одна сидируемая облигация не имела одновременно цены и доходности.
    _run(
        _seed_bcse_bond,
        internal_id="opt-full-path",
        price=Decimal("98.5"),
        yield_to_maturity=Decimal("12.5"),
        fetched_at=datetime.now(UTC),
    )
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
    assert len(body["allocations"]) > 0
    assert any(a["internal_id"] == "opt-full-path" for a in body["allocations"])
    for item in body["allocations"]:
        assert item["currency"] == "BYN"
        assert item["lots"] >= 1
        assert item["amount"] <= 50000.0
        assert item["weight_pct"] > 0
    assert len(body["order_tickets"]) == len(body["allocations"])
    for ticket in body["order_tickets"]:
        assert ticket["action"] == "BUY"
        assert ticket["currency"] == "BYN"


def test_demo_portfolio_optimize_moex_propagates_rub() -> None:
    _run(
        _seed_bcse_bond,
        internal_id="opt-moex-rub",
        market="moex",
        currency="RUB",
        nominal=Decimal("1000"),
        price=Decimal("985"),
        yield_to_maturity=Decimal("8.5"),
        fetched_at=datetime.now(UTC),
        is_government=False,
    )
    resp = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={
            "capital": 25000.0,
            "strategy": "Balanced",
            "currency": "RUB",
            "market": "moex",
            "top_n": 5,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["allocations"]) > 0
    for item in body["allocations"]:
        assert item["currency"] == "RUB"
        assert item["amount"] <= 25000.0


def test_demo_portfolio_optimize_zero_capital_warns() -> None:
    _run(
        _seed_bcse_bond,
        internal_id="opt-zero-cap",
        price=Decimal("98.5"),
        yield_to_maturity=Decimal("12.5"),
        fetched_at=datetime.now(UTC),
    )
    resp = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={"capital": 0.0, "strategy": "Balanced", "currency": "BYN"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allocations"] == []
    assert body["order_tickets"] == []
    assert "больше 0" in body["warning"]


def test_demo_portfolio_optimize_capital_below_one_lot_warns() -> None:
    _run(
        _seed_bcse_bond,
        internal_id="opt-below-lot",
        price=Decimal("98.5"),
        yield_to_maturity=Decimal("12.5"),
        fetched_at=datetime.now(UTC),
    )
    resp = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={"capital": 4.0, "strategy": "Balanced", "currency": "BYN"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allocations"] == []
    assert "меньше минимальной стоимости" in body["warning"]


# --- pure-unit проверки _build_impact на подменённых фикстурах ---


def test_demo_impact_missing_fixture_files_fall_back_gracefully(monkeypatch) -> None:
    from pathlib import Path

    import api.demo as demo_mod

    monkeypatch.setattr(demo_mod, "DATA_ROOT", Path("C:/definitely-not-a-real-demo-data"))
    assert demo_mod._load_manifest() == {}
    assert demo_mod._load_json("portfolio_templates.json") == []

    # Без файлов с бумагами портфель-импакт корректно отвечает 404.
    resp = client.post(
        "/api/v1/demo/portfolio-impact",
        json={"bond_id": "demo-bond-001", "allocation_pct": 10},
    )
    assert resp.status_code == 404


def test_demo_impact_fallback_template_and_long_duration_borderline(monkeypatch) -> None:
    import api.demo as demo_mod

    _orig_load_json = demo_mod._load_json

    def fake_load_json(name: str):
        if name == "portfolio_templates.json":
            # Шаблон с неизвестной структурой -> дефолтные бенчмарки 9.5%/2.4 года.
            return [{"mystery": True}]
        return _orig_load_json(name)

    monkeypatch.setattr(demo_mod, "_load_json", fake_load_json)
    bond = next(
        b for b in demo_mod._load_json("bonds_bcse.json") if b["internal_id"] == "demo-bond-001"
    )
    req = demo_mod.PortfolioImpactRequest(bond_id="demo-bond-001", allocation_pct=10)
    res = demo_mod._build_impact(req)
    assert res.before.expected_yield_pct == 9.5
    assert res.before.concentration_by_issuer == {"demo": 100.0}
    # Дюрация бумаги из фикстуры мала -> допустимо.
    assert res.risk_profile_fit in {"ok", "borderline"}

    # Долгая бумага (6 лет) -> borderline-предупреждение.
    def fake_load_json_long(name: str):
        if name == "portfolio_templates.json":
            return [{"mystery": True}]
        if name == "bonds_bcse.json":
            return [{**bond, "duration_years": 6.0}]
        return _orig_load_json(name)

    monkeypatch.setattr(demo_mod, "_load_json", fake_load_json_long)
    res = demo_mod._build_impact(req)
    assert res.risk_profile_fit == "borderline"
    assert "Дюрация" in res.concentration_warning


def test_demo_impact_concentration_off_when_issuer_exceeds_limit(monkeypatch) -> None:
    import api.demo as demo_mod

    issuer = "Министерство финансов Республики Беларусь"
    _orig_load_json = demo_mod._load_json

    def fake_load_json(name: str):
        if name == "portfolio_templates.json":
            return {
                "moderate_byn": {
                    "benchmarks": {
                        "expected_yield_pct": 10.0,
                        "duration_years": 2.5,
                        "issuer_concentration_max_pct": 25,
                    },
                    "positions": [{"name": issuer, "weight_pct": 90.0}],
                }
            }
        if name == "bonds_bcse.json":
            return [{"internal_id": "demo-bond-001", "issuer": issuer, "yield_to_maturity": 13.38}]
        return _orig_load_json(name)

    monkeypatch.setattr(demo_mod, "_load_json", fake_load_json)
    req = demo_mod.PortfolioImpactRequest(bond_id="demo-bond-001", allocation_pct=10)
    res = demo_mod._build_impact(req)
    assert res.before.concentration_by_issuer == {issuer: 90.0}
    assert res.risk_profile_fit == "off"
    assert "превысит 25%" in res.concentration_warning


def test_demo_impact_ok_when_concentration_stays_within_limit(monkeypatch) -> None:
    import api.demo as demo_mod

    _orig_load_json = demo_mod._load_json

    def fake_load_json(name: str):
        if name == "portfolio_templates.json":
            return {
                "moderate_byn": {
                    "benchmarks": {
                        "expected_yield_pct": 10.0,
                        "duration_years": 2.5,
                        "issuer_concentration_max_pct": 25,
                    },
                    "positions": [{"name": "Беларусбанк", "weight_pct": 10.0}],
                }
            }
        if name == "bonds_bcse.json":
            return [
                {
                    "internal_id": "demo-bond-001",
                    "issuer": "Газпром нефть",
                    "yield_to_maturity": 12.0,
                }
            ]
        return _orig_load_json(name)

    monkeypatch.setattr(demo_mod, "_load_json", fake_load_json)
    req = demo_mod.PortfolioImpactRequest(bond_id="demo-bond-001", allocation_pct=10)
    res = demo_mod._build_impact(req)
    assert res.risk_profile_fit == "ok"
    assert res.before.concentration_by_issuer == {"Беларусбанк": 10.0}
    assert "допустимо" in res.concentration_warning


def test_demo_impact_marina_legacy_template_key_still_works(monkeypatch) -> None:
    import api.demo as demo_mod

    _orig_load_json = demo_mod._load_json

    def fake_load_json(name: str):
        if name == "portfolio_templates.json":
            return {
                "marina_50000_byn": {
                    "benchmarks": {"expected_yield_pct": 11.0, "duration_years": 2.2},
                    "positions": [],
                }
            }
        if name == "bonds_bcse.json":
            return [
                {
                    "internal_id": "demo-bond-001",
                    "issuer": "Газпром нефть",
                    "yield_to_maturity": 12.0,
                }
            ]
        return _orig_load_json(name)

    monkeypatch.setattr(demo_mod, "_load_json", fake_load_json)
    req = demo_mod.PortfolioImpactRequest(bond_id="demo-bond-001", allocation_pct=10)
    res = demo_mod._build_impact(req)
    assert res.before.expected_yield_pct == 11.0
    assert res.before.duration_years == 2.2


# --- оптимизатор: распределение лотов и аварийные ветки ---


def test_demo_portfolio_optimize_allocate_failure_falls_back_to_greedy(monkeypatch) -> None:
    import portfolio.optimizer as optimizer_mod

    _run(
        _seed_bcse_bond,
        internal_id="opt-alloc-fail",
        price=Decimal("98.5"),
        yield_to_maturity=Decimal("13.5"),
        fetched_at=datetime.now(UTC),
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("allocate crashed")

    monkeypatch.setattr(optimizer_mod, "allocate", _boom)
    resp = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={"capital": 50000.0, "strategy": "Balanced", "currency": "BYN", "top_n": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Без скоринга выбираем по доходности и всё равно покупаем лоты.
    assert len(body["allocations"]) == 1
    assert body["allocations"][0]["internal_id"] == "opt-alloc-fail"
    assert body["allocations"][0]["lots"] >= 1


def test_demo_portfolio_optimize_greedy_single_lot_when_shares_round_to_zero() -> None:
    _run(
        _seed_bcse_bond,
        internal_id="opt-lot-a",
        price=Decimal("98.5"),
        yield_to_maturity=Decimal("12.5"),
        fetched_at=datetime.now(UTC),
    )
    _run(
        _seed_bcse_bond,
        internal_id="opt-lot-b",
        price=Decimal("98.5"),
        yield_to_maturity=Decimal("12.0"),
        fetched_at=datetime.now(UTC),
    )
    # 150 BYN на две бумаги: доля 75 < цены лота 98.5 -> по 0 лотов,
    # жадный проход докупает 1 лот лучшей бумаги.
    resp = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={"capital": 150.0, "strategy": "Balanced", "currency": "BYN", "top_n": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["allocations"]) == 1
    assert body["allocations"][0]["lots"] == 1
    assert body["allocations"][0]["amount"] <= 150.0


def test_demo_portfolio_optimize_redistributes_remainder_cash() -> None:
    _run(
        _seed_bcse_bond,
        internal_id="opt-rem-a",
        price=Decimal("98.5"),
        yield_to_maturity=Decimal("12.5"),
        fetched_at=datetime.now(UTC),
    )
    _run(
        _seed_bcse_bond,
        internal_id="opt-rem-b",
        price=Decimal("98.5"),
        yield_to_maturity=Decimal("12.0"),
        fetched_at=datetime.now(UTC),
    )
    # 300 BYN: по 1 лоту каждой (98.5*2=197), остаток 103 >= 98.5 ->
    # топ-бумага получает ещё один лот.
    resp = client.post(
        "/api/v1/demo/portfolio/optimize",
        json={"capital": 300.0, "strategy": "Balanced", "currency": "BYN", "top_n": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["allocations"]) == 2
    total_lots = sum(a["lots"] for a in body["allocations"])
    total_spent = sum(a["amount"] for a in body["allocations"])
    assert total_lots == 3
    assert total_spent <= 300.0


def test_demo_portfolio_optimize_dollarization_and_metals_on_moex() -> None:
    _run(
        _seed_bcse_bond,
        internal_id="opt-moex-usd",
        market="moex",
        currency="USD",
        nominal=Decimal("1000"),
        price=Decimal("900"),
        yield_to_maturity=Decimal("9.0"),
        fetched_at=datetime.now(UTC),
        is_government=False,
    )
    for strategy in ["Dollarization", "Metals++"]:
        resp = client.post(
            "/api/v1/demo/portfolio/optimize",
            json={
                "capital": 20000.0,
                "strategy": strategy,
                "currency": "USD",
                "market": "moex",
                "top_n": 5,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        # USD-бумага попадает в выборку MOEX-ветки обеих стратегий.
        assert any(a["internal_id"] == "opt-moex-usd" for a in body["allocations"])


def test_demo_desk_stress_mixed_market_uses_majority_currency() -> None:
    _run(
        _seed_bcse_bond,
        internal_id="mix-bcse",
        price=Decimal("98.5"),
        yield_to_maturity=Decimal("12.5"),
        fetched_at=datetime.now(UTC),
    )
    _run(
        _seed_bcse_bond,
        internal_id="mix-moex",
        market="moex",
        currency="RUB",
        nominal=Decimal("1000"),
        price=Decimal("985"),
        yield_to_maturity=Decimal("8.5"),
        fetched_at=datetime.now(UTC),
        is_government=False,
    )
    resp = client.post(
        "/api/v1/demo/desk/stress",
        json={"scenario": "parallel_+100bp", "market": "mixed", "capital": 100000.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["duration_before"] > 0
    assert len(body["positions"]) > 0
    assert body["by_position"] != {}
