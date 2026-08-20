"""Cross-module data-consistency invariants (math must agree across modules)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from desk.carry import carry_for_bond
from desk.cashflow import accrued_interest, pricing_cashflows
from desk.duration import bond_modified_duration, duration_report
from desk.ytm import ytm_from_price
from ml.features import build_features
from portfolio.pnl import compute_pnl
from scoring.engine import score_bond
from scoring.models import BondScore


def _bond(
    internal_id="B",
    ytm=10.0,
    coupon=10.0,
    price=100.0,
    currency="BYN",
    maturity=date(2028, 1, 1),
    start=date(2024, 1, 1),
    freq=2,
    nominal=1000,
):
    return SimpleNamespace(
        internal_id=internal_id,
        yield_to_maturity=ytm,
        coupon_rate=coupon,
        coupon_frequency=freq,
        price=price,
        currency=currency,
        start_date=start,
        maturity_date=maturity,
        nominal=nominal,
    )


def test_modified_duration_agrees_between_helpers():
    b = _bond()
    d1 = bond_modified_duration(b, asof=date(2024, 1, 1))
    d2 = duration_report(b, asof=date(2024, 1, 1)).modified_duration
    assert d1 == pytest.approx(d2, abs=1e-4)


def test_ml_features_duration_matches_engine():
    b = _bond()
    f = build_features(
        bond_dict={
            "internal_id": "B",
            "currency": "BYN",
            "yield_to_maturity": 10.0,
            "price": 100.0,
            "coupon_rate": 10.0,
            "maturity_date": date(2028, 1, 1),
            "issuer": "ООО Рога",
            "status": "active",
            "nominal": 1000,
            "coupon_frequency": 2,
            "start_date": date(2024, 1, 1),
        },
        asof=date(2024, 1, 1),
    )
    assert f.modified_duration == pytest.approx(
        bond_modified_duration(b, asof=date(2024, 1, 1)), abs=1e-4
    )


def test_ml_features_score_matches_scoring_engine():
    bd = {
        "internal_id": "B",
        "currency": "BYN",
        "yield_to_maturity": 12.0,
        "price": 100.0,
        "coupon_rate": 12.0,
        "maturity_date": date(2028, 1, 1),
        "issuer": "ООО Рога",
        "status": "active",
        "nominal": 1000,
        "coupon_frequency": 2,
        "start_date": date(2024, 1, 1),
    }
    f = build_features(bond_dict=bd, asof=date(2024, 1, 1))
    # NOTE: build_features' internal score_bond call forwards only internal_id,
    # ytm, currency, maturity, status, issuer and price - NOT ref_date, nominal
    # or coupon_rate. Mirror that exactly so the two scores use identical inputs.
    direct = score_bond(
        internal_id="B",
        yield_to_maturity=12.0,
        currency="BYN",
        maturity_date=date(2028, 1, 1),
        status="active",
        issuer="ООО Рога",
        price=100.0,
    )
    assert f.score == pytest.approx(direct.score, abs=1e-6)


def test_scoring_risk_adjusted_equals_efficiency_times_six():
    sc: BondScore = score_bond(
        internal_id="B",
        yield_to_maturity=12.0,
        currency="BYN",
        maturity_date=date(2028, 1, 1),
        status="active",
        coupon_rate=12.0,
        price=100.0,
    )
    assert sc.risk_adjusted_score == pytest.approx(sc.breakdown.efficiency_ratio * 6.0, abs=0.01)


def test_pnl_round_trip_zero_at_same_price():
    txs = [
        SimpleNamespace(
            internal_id="B",
            side="buy",
            amount=Decimal("1000"),
            price=Decimal("100"),
            executed_at=datetime(2024, 1, 1),
        ),
        SimpleNamespace(
            internal_id="B",
            side="sell",
            amount=Decimal("1000"),
            price=Decimal("100"),
            executed_at=datetime(2024, 2, 1),
        ),
    ]
    res = compute_pnl(txs, [_pos("B", 1000)], {"B": _bond()})
    pos = next(p for p in res.per_bond if p.internal_id == "B")
    # buy and sell at the same clean price => realized P&L ~ 0
    assert abs(pos.realized_pnl) < Decimal("1")


def test_carry_pnl_sign_follows_coupon_minus_funding():
    carry_bond = SimpleNamespace(
        internal_id="B",
        yield_to_maturity=12.0,
        coupon_rate=12.0,
        coupon_frequency=2,
        maturity_date=date(2028, 1, 1),
        start_date=date(2024, 1, 1),
        nominal=Decimal("1000"),
        currency="BYN",
    )
    earn = carry_for_bond(carry_bond, funding_rate_pct=8.0, horizon_days=365, asof=date(2024, 1, 1))
    lose = carry_for_bond(
        carry_bond, funding_rate_pct=20.0, horizon_days=365, asof=date(2024, 1, 1)
    )
    assert earn.expected_pnl_pct > 0
    assert lose.expected_pnl_pct < 0


def test_ytm_solver_consistent_with_cashflow_pricer():
    # Solve YTM from a price, then discount the same cashflows at that YTM and
    # recover (approximately) the original clean price — the solver and the
    # pricer must agree.
    asof = date(2024, 1, 1)
    maturity = date(2029, 1, 1)
    coupon, freq, price = 10.0, 2, 100.0
    ytm = ytm_from_price(price, coupon, freq, maturity, asof=asof)
    assert ytm is not None
    flows = pricing_cashflows(
        nominal=100.0,
        coupon_rate_pct=coupon,
        coupon_frequency=freq,
        maturity=maturity,
        asof=asof,
        issue_date=date(2024, 1, 1),
    )
    accrued = accrued_interest(
        coupon_rate_pct=coupon,
        coupon_frequency=freq,
        issue_date=date(2024, 1, 1),
        maturity_date=maturity,
        asof=asof,
        face=100.0,
    )
    # pricing_cashflows returns (years_from_asof, amount); discount at the solved YTM
    pv = Decimal("0")
    for years, amt in flows:
        disc = Decimal(str((1.0 + ytm / 100.0) ** -years))
        pv += Decimal(str(amt)) * disc
    clean_pv = pv - Decimal(str(accrued))
    assert clean_pv == pytest.approx(Decimal(str(price)), abs=2.0)


def _pos(iid, amount):
    return SimpleNamespace(internal_id=iid, amount=Decimal(str(amount)))
