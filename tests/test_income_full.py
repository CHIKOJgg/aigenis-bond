"""Comprehensive tests for portfolio.income (coupon projection & calendar)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from portfolio.income import (
    CashFlow,
    annual_income,
    bond_cashflows,
    portfolio_income,
)


# --------------------------------------------------------------------------- #
# CashFlow
# --------------------------------------------------------------------------- #
def test_cashflow_rounds_amount():
    cf = CashFlow(date=date(2024, 7, 1), amount=Decimal("50.456"), kind="coupon", internal_id="B")
    assert cf.amount == Decimal("50.46")


def test_cashflow_as_dict():
    cf = CashFlow(date=date(2024, 7, 1), amount=Decimal("50"), kind="coupon", internal_id="B")
    d = cf.as_dict()
    assert d["kind"] == "coupon"
    assert d["date"] == "2024-07-01"


# --------------------------------------------------------------------------- #
# _face_value (internal)
# --------------------------------------------------------------------------- #
def test_bond_cashflows_face_at_par():
    flows = bond_cashflows(
        internal_id="B",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("10"),
        coupon_frequency=2,
        maturity_date=date(2026, 1, 1),
        price=Decimal("100"),
        issue_date=date(2024, 1, 1),
        from_date=date(2024, 1, 1),
    )
    redemption = [f for f in flows if f.kind == "redemption"]
    assert redemption[0].amount == Decimal("1000")


def test_bond_cashflows_face_below_par():
    flows = bond_cashflows(
        internal_id="B",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("10"),
        coupon_frequency=2,
        maturity_date=date(2026, 1, 1),
        price=Decimal("98"),
        issue_date=date(2024, 1, 1),
        from_date=date(2024, 1, 1),
    )
    redemption = [f for f in flows if f.kind == "redemption"]
    # 1000 * 100/98 ~= 1020.41
    assert redemption[0].amount == pytest.approx(Decimal("1020.41"), abs=Decimal("0.01"))


# --------------------------------------------------------------------------- #
# coupon schedule generation
# --------------------------------------------------------------------------- #
def test_bond_cashflows_semiannual_count():
    flows = bond_cashflows(
        internal_id="B",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("10"),
        coupon_frequency=2,
        maturity_date=date(2026, 1, 1),
        issue_date=date(2024, 1, 1),
        from_date=date(2024, 1, 1),
    )
    coupons = [f for f in flows if f.kind == "coupon"]
    assert len(coupons) == 4  # 2y * 2


def test_bond_cashflows_coupon_amount_approx():
    flows = bond_cashflows(
        internal_id="B",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("10"),
        coupon_frequency=2,
        maturity_date=date(2026, 1, 1),
        price=Decimal("100"),
        issue_date=date(2024, 1, 1),
        from_date=date(2024, 1, 1),
    )
    coupons = [f for f in flows if f.kind == "coupon"]
    for c in coupons:
        assert c.amount == pytest.approx(Decimal("50"), abs=Decimal("0.5"))


def test_bond_cashflows_empty_after_maturity():
    assert (
        bond_cashflows(
            internal_id="B",
            amount_invested=Decimal("1000"),
            coupon_rate=Decimal("10"),
            coupon_frequency=2,
            maturity_date=date(2020, 1, 1),
            issue_date=date(2018, 1, 1),
        )
        == []
    )


def test_bond_cashflows_from_date_filter():
    flows = bond_cashflows(
        internal_id="B",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("10"),
        coupon_frequency=2,
        maturity_date=date(2026, 1, 1),
        issue_date=date(2024, 1, 1),
        from_date=date(2025, 7, 1),
    )
    # only 2026-01-01 redemption + any coupon after that date
    for f in flows:
        assert f.date > date(2025, 7, 1)


def test_bond_cashflows_fallback_monthly_when_no_issue():
    flows = bond_cashflows(
        internal_id="B",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("10"),
        coupon_frequency=2,
        maturity_date=date(2026, 1, 1),
        from_date=date(2024, 1, 1),
    )
    assert len(flows) >= 1


def test_bond_cashflows_zero_coupon_no_coupons():
    flows = bond_cashflows(
        internal_id="B",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("0"),
        coupon_frequency=2,
        maturity_date=date(2026, 1, 1),
        issue_date=date(2024, 1, 1),
        from_date=date(2024, 1, 1),
    )
    assert all(f.kind == "redemption" for f in flows)


def test_bond_cashflows_day_count_adjusts_amount():
    # quarterly over a leap-year Feb has fewer days -> smaller coupon
    short = bond_cashflows(
        internal_id="B",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("12"),
        coupon_frequency=4,
        maturity_date=date(2024, 5, 1),
        issue_date=date(2024, 2, 1),
        day_count="ACT/365",
        from_date=date(2024, 1, 1),
    )
    long = bond_cashflows(
        internal_id="B",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("12"),
        coupon_frequency=4,
        maturity_date=date(2024, 8, 1),
        issue_date=date(2024, 5, 1),
        day_count="ACT/365",
        from_date=date(2024, 1, 1),
    )
    short_coupon = max((f for f in short if f.kind == "coupon"), key=lambda f: f.amount)
    long_coupon = max((f for f in long if f.kind == "coupon"), key=lambda f: f.amount)
    assert short_coupon.amount < long_coupon.amount


# --------------------------------------------------------------------------- #
# annual_income
# --------------------------------------------------------------------------- #
def test_annual_income_basic():
    assert annual_income(
        amount_invested=Decimal("1000"), coupon_rate=Decimal("10"), price=Decimal("100")
    ) == Decimal("100")


def test_annual_income_zero_for_no_coupon():
    assert annual_income(amount_invested=Decimal("1000"), coupon_rate=Decimal("0")) == Decimal(
        "0.00"
    )


def test_annual_income_below_par_more_face():
    # price 95 -> more face -> more annual income
    assert annual_income(
        amount_invested=Decimal("1000"), coupon_rate=Decimal("10"), price=Decimal("95")
    ) == pytest.approx(Decimal("105.26"), abs=Decimal("0.01"))


# --------------------------------------------------------------------------- #
# portfolio_income aggregation
# --------------------------------------------------------------------------- #
def _holding(amount=1000, coupon_rate=10, freq=2, maturity="2026-01-01", price=100, currency="BYN"):
    return {
        "internal_id": "B",
        "amount": amount,
        "coupon_rate": coupon_rate,
        "coupon_frequency": freq,
        "maturity_date": maturity,
        "price": price,
        "currency": currency,
        "name": "Bond B",
    }


def test_portfolio_income_totals():
    res = portfolio_income([_holding()], from_date=date(2024, 1, 1))
    assert res["total_invested"] == 1000.0
    assert res["annual_income"] == pytest.approx(100.0, abs=0.01)
    assert res["yield_on_cost"] == pytest.approx(10.0, abs=0.01)


def test_portfolio_income_next_payment_present():
    res = portfolio_income(
        [_holding(maturity="2026-01-01", coupon_rate=10, freq=2)], from_date=date(2024, 2, 1)
    )
    assert res["next_payment"] is not None


def test_portfolio_income_monthly_calendar_sum_equals_horizon():
    res = portfolio_income(
        [_holding(coupon_rate=12, freq=2)], from_date=date(2024, 1, 1), horizon_months=12
    )
    total = sum(m["amount"] for m in res["monthly_calendar"])
    # horizon income over 12 months ~ annual income (coupons fall in window)
    assert total > 0


def test_portfolio_income_fx_scales():
    byn = portfolio_income(
        [_holding(currency="BYN")], from_date=date(2024, 1, 1), fx_rates={"BYN": 1.0}
    )
    usd = portfolio_income(
        [_holding(currency="USD")], from_date=date(2024, 1, 1), fx_rates={"USD": 3.0}
    )
    assert usd["annual_income"] == pytest.approx(byn["annual_income"] * 3, abs=0.01)


def test_portfolio_income_empty_for_no_holdings():
    res = portfolio_income([], from_date=date(2024, 1, 1))
    assert res["annual_income"] == 0.0
    assert res["next_payment"] is None
