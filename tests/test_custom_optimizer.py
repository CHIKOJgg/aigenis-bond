"""Unit tests for the user-defined portfolio optimizer / calculator engine."""

from __future__ import annotations

from datetime import date, timedelta

from portfolio.custom_optimizer import (
    bond_current_yield,
    bond_duration,
    bond_ytm,
    calculate_fixed,
    compute_portfolio_metrics,
    discrete_allocate,
    optimize_weights,
)


class FakeBond:
    def __init__(
        self,
        internal_id: str,
        ytm: float,
        coupon: float,
        price: float = 100.0,
        nominal: float = 1000.0,
        maturity_days: int = 365 * 3,
        currency: str = "BYN",
        issuer: str = "Issuer",
        duration_years: float | None = None,
    ) -> None:
        self.internal_id = internal_id
        self.yield_to_maturity = ytm
        self.coupon_rate = coupon
        self.price = price
        self.nominal = nominal
        self.currency = currency
        self.issuer = issuer
        self.indexation_currency = None
        self.start_date = date.today() - timedelta(days=365)
        self.maturity_date = date.today() + timedelta(days=maturity_days)
        self.duration_years = duration_years
        self.current_yield = None


def _bonds() -> list[FakeBond]:
    return [
        FakeBond("B1", ytm=8.0, coupon=8.0, price=100.0, maturity_days=365 * 2, issuer="Govt"),
        FakeBond("B2", ytm=12.0, coupon=12.0, price=95.0, maturity_days=365 * 5, issuer="CorpA"),
        FakeBond("B3", ytm=10.0, coupon=10.0, price=98.0, maturity_days=365 * 8, issuer="CorpB"),
    ]


def test_optimize_weights_equal_sums_to_one():
    w = optimize_weights(_bonds(), "equal_weight")
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert len(w) == 3
    assert all(abs(v - 1 / 3) < 1e-9 for v in w.values())


def test_optimize_weights_min_variance_favors_low_vol():
    # B1 has short maturity => lower vol => higher weight under min_variance
    w = optimize_weights(_bonds(), "min_variance")
    assert w["B1"] > w["B3"]


def test_optimize_weights_risk_parity_distinct_from_min_variance():
    mv = optimize_weights(_bonds(), "min_variance")
    rp = optimize_weights(_bonds(), "risk_parity")
    assert abs(mv["B1"] - rp["B1"]) > 1e-6


def test_optimize_weights_unknown_objective_falls_back():
    w = optimize_weights(_bonds(), "nonsense")
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_optimize_weights_empty():
    assert optimize_weights([], "equal_weight") == {}


def test_compute_portfolio_metrics_sane():
    bonds = _bonds()
    w = optimize_weights(bonds, "equal_weight")
    m = compute_portfolio_metrics(bonds, w)
    # weighted YTM is between min and max of constituents
    assert 8.0 <= m["expected_return"] <= 12.0
    assert m["volatility"] > 0
    assert m["concentration_by_issuer"]
    assert abs(sum(m["concentration_by_issuer"].values()) - 100.0) < 0.5
    assert m["weighted_duration"] > 0


def test_compute_portfolio_metrics_zero_weights():
    bonds = _bonds()
    m = compute_portfolio_metrics(bonds, {b.internal_id: 0.0 for b in bonds})
    assert m["expected_return"] == 0.0


def test_discrete_allocate_produces_orders():
    bonds = _bonds()
    w = optimize_weights(bonds, "equal_weight")
    items, orders = discrete_allocate(bonds, w, 50000.0, currency="BYN")
    assert len(items) == 3
    assert len(orders) == 3
    total_cost = sum(i["amount"] for i in items)
    # allocated close to capital (within one cheapest lot)
    assert total_cost <= 50000.0
    assert total_cost > 0
    weights = [i["weight_pct"] for i in items]
    assert abs(sum(weights) - 100.0) < 1.0


def test_calculate_fixed_uses_amounts():
    bonds = _bonds()
    holdings = [("B1", 30000.0), ("B2", 20000.0)]
    m = calculate_fixed(bonds, holdings)
    assert m["holdings"][0]["weight_pct"] == 60.0
    assert m["holdings"][1]["weight_pct"] == 40.0
    assert abs(sum(h["weight_pct"] for h in m["holdings"]) - 100.0) < 1e-6


def test_bond_helpers():
    b = FakeBond("X", ytm=10.0, coupon=8.0, price=100.0)
    # Цена = номинал: честный YTM ≈ купон (8.0), а не устаревший фидовый 10.0.
    assert abs(bond_ytm(b) - 8.0) < 0.1
    assert bond_current_yield(b) == 8.0
    assert bond_duration(b) > 0


def test_bond_ytm_honest_negative():
    b = FakeBond("X", ytm=10.0, coupon=10.0, price=102.61, maturity_days=42)
    assert bond_ytm(b) < 0.0
