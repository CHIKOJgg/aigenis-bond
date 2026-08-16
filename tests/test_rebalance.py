"""Tests for portfolio.rebalance pure helpers (drift detection / plan weights)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import portfolio.rebalance as rb


def _pos(internal_id, amount):
    return SimpleNamespace(internal_id=internal_id, amount=Decimal(str(amount)))


def test_compute_weights_delta_and_before_after():
    positions = [_pos("A", 600), _pos("B", 400)]
    target = {"A": Decimal("500"), "B": Decimal("500")}
    weights = rb._compute_weights(positions, target, total=Decimal("1000"))
    assert weights["A"][0] == Decimal("-100")  # A reduced
    assert weights["B"][0] == Decimal("100")   # B increased
    # weight_before for A = 600/1000 = 0.6
    assert weights["A"][1] == pytest.approx(0.6)
    assert weights["B"][2] == pytest.approx(0.5)


def test_compute_weights_new_target_id():
    positions = [_pos("A", 1000)]
    target = {"A": Decimal("800"), "C": Decimal("200")}
    weights = rb._compute_weights(positions, target, total=Decimal("1000"))
    assert "C" in weights
    assert weights["C"][0] == Decimal("200")


def test_drift_is_max_abs_weight_change():
    deltas = {
        "A": (Decimal("-100"), 0.6, 0.5),
        "B": (Decimal("100"), 0.4, 0.5),
    }
    assert rb._drift(deltas) == pytest.approx(0.1)


def test_drift_zero_when_empty():
    assert rb._drift({}) == 0.0


def test_build_plan_none_when_below_threshold():
    from scoring.models import UserPreferences

    bonds = [_bond("A", ytm=10), _bond("B", ytm=12)]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("1000"),
                            strategy="Balanced")
    plan = rb.build_plan(bonds=bonds, prefs=prefs,
                         current_positions=[_pos("A", 500), _pos("B", 500)],
                         current_total=Decimal("1000"), drift_threshold=0.05)
    # Already balanced (50/50) -> no drift above 5%
    assert plan is None


def test_build_plan_returns_actions_when_drifted():
    from scoring.models import UserPreferences

    bonds = [_bond("A", ytm=10), _bond("B", ytm=12)]
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("1000"),
                            strategy="Balanced")
    plan = rb.build_plan(bonds=bonds, prefs=prefs,
                         current_positions=[_pos("A", 900), _pos("B", 100)],
                         current_total=Decimal("1000"), drift_threshold=0.05)
    assert plan is not None
    assert plan.max_drift_observed > 0.05
    sides = {a.internal_id: a.side for a in plan.actions}
    assert sides["A"] == "sell"
    assert sides["B"] == "buy"


def _bond(internal_id, ytm, currency="BYN"):
    from datetime import date
    from types import SimpleNamespace

    return SimpleNamespace(
        internal_id=internal_id,
        name=internal_id,
        issuer=None,
        yield_to_maturity=ytm,
        coupon_rate=10.0,
        coupon_frequency=2,
        currency=currency,
        price=100.0,
        nominal=1000,
        start_date=date(2024, 1, 1),
        maturity_date=date(2028, 1, 1),
        status="active",
        is_government=False,
    )


import pytest  # noqa: E402
