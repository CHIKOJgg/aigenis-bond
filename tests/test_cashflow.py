"""Tests for day-count conventions, coupon schedules and accrued interest."""

from __future__ import annotations

from datetime import date

from desk.cashflow import (
    accrued_interest,
    coupon_dates,
    pricing_cashflows,
    year_fraction,
)


def test_year_fraction_30_360():
    # 6 months apart -> exactly 0.5 under 30/360.
    assert year_fraction(date(2024, 1, 1), date(2024, 7, 1), "30/360") == 0.5
    # A full year -> 1.0
    assert year_fraction(date(2024, 1, 1), date(2025, 1, 1), "30/360") == 1.0


def test_year_fraction_act_conventions():
    d1 = date(2024, 1, 1)
    d2 = date(2024, 1, 2)
    assert abs(year_fraction(d1, d2, "ACT/365") - 1 / 365) < 1e-9
    assert abs(year_fraction(d1, d2, "ACT/360") - 1 / 360) < 1e-9
    # 2024 is a leap year -> ACT/ACT divides by 366.
    assert abs(year_fraction(d1, d2, "ACT/ACT") - 1 / 366) < 1e-9


def test_coupon_dates_include_maturity():
    dates = coupon_dates(date(2024, 1, 1), date(2030, 1, 1), 2)
    assert dates[0] == date(2024, 1, 1)
    assert dates[-1] == date(2030, 1, 1)
    # Semi-annual -> 1 (issue) + 11 mid + 1 maturity = 13 entries.
    assert len(dates) == 13


def test_accrued_interest_mid_period():
    # 8% semiannual, asof exactly halfway -> ~half a coupon per 100 par.
    ai = accrued_interest(
        coupon_rate_pct=8.0,
        coupon_frequency=2,
        issue_date=date(2024, 1, 1),
        maturity_date=date(2030, 1, 1),
        asof=date(2024, 4, 1),
        convention="ACT/365",
        face=100.0,
    )
    # prev coupon 2024-01-01, next 2024-07-01 => exactly half the period.
    assert abs(ai - 2.0) < 1e-6


def test_accrued_interest_zero_for_zero_coupon():
    ai = accrued_interest(
        coupon_rate_pct=0.0,
        coupon_frequency=2,
        issue_date=date(2024, 1, 1),
        maturity_date=date(2030, 1, 1),
        asof=date(2024, 4, 1),
    )
    assert ai == 0.0


def test_pricing_cashflows_has_redemption_and_timing():
    flows = pricing_cashflows(
        nominal=1000.0,
        coupon_rate_pct=8.0,
        coupon_frequency=2,
        maturity=date(2030, 1, 1),
        asof=date(2026, 1, 1),
        issue_date=date(2024, 1, 1),
    )
    assert flows
    # Last flow includes the redemption (nominal).
    assert flows[-1][1] > 1000.0
    # Timings are increasing.
    ts = [t for t, _ in flows]
    assert ts == sorted(ts)
    # All future (positive time from asof).
    assert all(t > 0 for t in ts)


def test_pricing_cashflows_fallback_without_issue_date():
    flows = pricing_cashflows(
        nominal=1000.0,
        coupon_rate_pct=8.0,
        coupon_frequency=2,
        maturity=date(2030, 1, 1),
        asof=date(2026, 1, 1),
    )
    assert flows
    assert flows[-1][1] > 1000.0
