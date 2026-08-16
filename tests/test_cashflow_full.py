"""Comprehensive tests for desk.cashflow (day-count, coupon schedule, accrued)."""

from __future__ import annotations

from datetime import date

import pytest

from desk.cashflow import (
    CONVENTIONS,
    DEFAULT_DAY_COUNT,
    _add_months,
    _is_leap,
    accrued_interest,
    coupon_dates,
    pricing_cashflows,
    year_fraction,
)


# --------------------------------------------------------------------------- #
# Leap year helper
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "year,expected",
    [(2000, True), (2400, True), (1900, False), (2100, False), (2024, True), (2023, False)],
)
def test_is_leap(year, expected):
    assert _is_leap(year) is expected


# --------------------------------------------------------------------------- #
# _add_months
# --------------------------------------------------------------------------- #
def test_add_months_rolls_year():
    assert _add_months(date(2024, 11, 15), 3) == date(2025, 2, 15)


def test_add_months_clamps_day_to_month_end():
    # Jan 31 + 1 month -> Feb 28 (2023 not leap)
    assert _add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)
    # Jan 31 + 1 month leap -> Feb 29
    assert _add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_add_months_negative():
    assert _add_months(date(2024, 1, 15), -2) == date(2023, 11, 15)


# --------------------------------------------------------------------------- #
# year_fraction conventions
# --------------------------------------------------------------------------- #
def test_year_fraction_default_convention_is_act365():
    assert DEFAULT_DAY_COUNT == "ACT/365"


def test_year_fraction_rejects_unknown_convention_gracefully():
    # Unknown convention falls through to ACT/ACT branch (no exception).
    assert year_fraction(date(2024, 1, 1), date(2024, 1, 2), "NONSENSE") >= 0


def test_year_fraction_returns_zero_when_reversed():
    assert year_fraction(date(2024, 6, 1), date(2024, 1, 1)) == 0.0


def test_act365_basic():
    assert year_fraction(date(2024, 1, 1), date(2024, 1, 2), "ACT/365") == pytest.approx(1 / 365)


def test_act365_full_year_non_leap():
    assert year_fraction(date(2023, 1, 1), date(2024, 1, 1)) == pytest.approx(1.0)


def test_act360_basic():
    assert year_fraction(date(2024, 1, 1), date(2024, 1, 2), "ACT/360") == pytest.approx(1 / 360)


@pytest.mark.parametrize(
    "d1,d2",
    [
        (date(2024, 1, 31), date(2024, 2, 29)),
        (date(2024, 1, 31), date(2024, 7, 31)),
        (date(2023, 1, 31), date(2023, 2, 28)),
        (date(2024, 3, 31), date(2024, 9, 30)),
    ],
)
def test_thirty_360_month_end_rule(d1, d2):
    # 30/360 clamps both day-ends to 30.
    expected = (
        360 * (d2.year - d1.year)
        + 30 * (d2.month - d1.month)
        + (min(d2.day, 30) - min(d1.day, 30))
    ) / 360.0
    assert year_fraction(d1, d2, "30/360") == pytest.approx(expected)


def test_thirty_360_known_value():
    # 2024-01-01 -> 2024-03-15 : 2 months + 14 days -> (60+14)/360
    assert year_fraction(date(2024, 1, 1), date(2024, 3, 15), "30/360") == pytest.approx(
        (2 * 30 + 14) / 360
    )


def test_act_act_same_year_uses_calendar_days():
    assert year_fraction(date(2024, 1, 1), date(2024, 12, 31), "ACT/ACT") == pytest.approx(365 / 366)


def test_act_act_spanning_years():
    yf = year_fraction(date(2023, 12, 31), date(2024, 1, 1), "ACT/ACT")
    assert yf == pytest.approx(1 / 365)


def test_act_act_two_full_years():
    # 2023 (365) + 2024 (366)
    yf = year_fraction(date(2023, 1, 1), date(2025, 1, 1), "ACT/ACT")
    assert yf == pytest.approx(1 + 366 / 366)


def test_all_conventions_listed():
    assert set(CONVENTIONS) == {"30/360", "ACT/360", "ACT/365", "ACT/ACT"}


# --------------------------------------------------------------------------- #
# coupon_dates
# --------------------------------------------------------------------------- #
def test_coupon_dates_semiannual():
    cds = coupon_dates(date(2024, 1, 1), date(2026, 1, 1), 2)
    assert cds[0] == date(2024, 1, 1)
    assert cds[-1] == date(2026, 1, 1)
    assert cds == [
        date(2024, 1, 1),
        date(2024, 7, 1),
        date(2025, 1, 1),
        date(2025, 7, 1),
        date(2026, 1, 1),
    ]


@pytest.mark.parametrize("freq", [1, 2, 4, 12])
def test_coupon_dates_count_matches_frequency(freq):
    cds = coupon_dates(date(2024, 1, 1), date(2026, 1, 1), freq)
    # years=2 -> 2*freq + 1 inclusive dates
    assert len(cds) == 2 * freq + 1


def test_coupon_dates_invalid_frequency_defaults_to_semiannual():
    cds = coupon_dates(date(2024, 1, 1), date(2024, 7, 1), 99)
    assert len(cds) == 2  # issue + maturity only


# --------------------------------------------------------------------------- #
# accrued_interest
# --------------------------------------------------------------------------- #
def test_accrued_zero_before_issue():
    assert (
        accrued_interest(
            coupon_rate_pct=10,
            coupon_frequency=2,
            issue_date=date(2024, 6, 1),
            maturity_date=date(2026, 6, 1),
            asof=date(2024, 5, 1),
        )
        == 0.0
    )


def test_accrued_zero_after_maturity():
    assert (
        accrued_interest(
            coupon_rate_pct=10,
            coupon_frequency=2,
            issue_date=date(2024, 6, 1),
            maturity_date=date(2026, 6, 1),
            asof=date(2026, 7, 1),
        )
        == 0.0
    )


def test_accrued_zero_on_coupon_date():
    # asof exactly on a coupon date -> elapsed fraction 0
    assert (
        accrued_interest(
            coupon_rate_pct=10,
            coupon_frequency=2,
            issue_date=date(2024, 1, 1),
            maturity_date=date(2026, 1, 1),
            asof=date(2024, 7, 1),
        )
        == 0.0
    )


def test_accrued_zero_coupon_rate():
    assert (
        accrued_interest(
            coupon_rate_pct=0,
            coupon_frequency=2,
            issue_date=date(2024, 1, 1),
            maturity_date=date(2026, 1, 1),
            asof=date(2024, 4, 1),
        )
        == 0.0
    )


def test_accrued_zero_frequency():
    assert (
        accrued_interest(
            coupon_rate_pct=10,
            coupon_frequency=0,
            issue_date=date(2024, 1, 1),
            maturity_date=date(2026, 1, 1),
            asof=date(2024, 4, 1),
        )
        == 0.0
    )


def test_accrued_half_period_semiannual():
    # 10% semiannual, face 100. Coupon per period = 100*10/100/2 = 5.
    # asof exactly halfway (2024-04-01) between 2024-01-01 and 2024-07-01 => frac 0.5
    # ACT/365: period days = 182, elapsed = 91 -> frac=0.5
    ai = accrued_interest(
        coupon_rate_pct=10,
        coupon_frequency=2,
        issue_date=date(2024, 1, 1),
        maturity_date=date(2026, 1, 1),
        asof=date(2024, 4, 1),
    )
    assert ai == pytest.approx(2.5, abs=1e-6)


def test_accrued_full_period_30_360():
    # 12% annual paid annually, 30/360. Coupon per period = 12.
    # asof 6 months in -> exactly half -> 6.0
    ai = accrued_interest(
        coupon_rate_pct=12,
        coupon_frequency=1,
        issue_date=date(2024, 1, 1),
        maturity_date=date(2025, 1, 1),
        asof=date(2024, 7, 1),
        convention="30/360",
    )
    assert ai == pytest.approx(6.0, abs=1e-6)


def test_accrued_scales_with_face():
    base = accrued_interest(
        coupon_rate_pct=10,
        coupon_frequency=2,
        issue_date=date(2024, 1, 1),
        maturity_date=date(2026, 1, 1),
        asof=date(2024, 4, 1),
        face=100.0,
    )
    doubled = accrued_interest(
        coupon_rate_pct=10,
        coupon_frequency=2,
        issue_date=date(2024, 1, 1),
        maturity_date=date(2026, 1, 1),
        asof=date(2024, 4, 1),
        face=1000.0,
    )
    assert doubled == pytest.approx(base * 10)


# --------------------------------------------------------------------------- #
# pricing_cashflows
# --------------------------------------------------------------------------- #
def test_pricing_cashflows_empty_when_matured():
    assert (
        pricing_cashflows(
            nominal=1000,
            coupon_rate_pct=10,
            coupon_frequency=2,
            maturity=date(2020, 1, 1),
            asof=date(2024, 1, 1),
        )
        == []
    )


def test_pricing_cashflows_includes_redemption():
    flows = pricing_cashflows(
        nominal=1000,
        coupon_rate_pct=10,
        coupon_frequency=2,
        maturity=date(2026, 1, 1),
        asof=date(2024, 1, 1),
        issue_date=date(2024, 1, 1),
    )
    # last flow includes nominal redemption
    assert flows[-1][1] == pytest.approx(1000 + 50)


def test_pricing_cashflows_coupon_amount():
    flows = pricing_cashflows(
        nominal=1000,
        coupon_rate_pct=10,
        coupon_frequency=2,
        maturity=date(2026, 1, 1),
        asof=date(2024, 1, 1),
        issue_date=date(2024, 1, 1),
    )
    # each coupon = 1000*10/100/2 = 50
    for _t, amt in flows:
        if abs(amt - (1000 + 50)) > 1e-6:  # not the redemption flow
            assert amt == pytest.approx(50)


def test_pricing_cashflows_first_after_asof():
    flows = pricing_cashflows(
        nominal=1000,
        coupon_rate_pct=10,
        coupon_frequency=2,
        maturity=date(2026, 1, 1),
        asof=date(2024, 3, 1),
        issue_date=date(2024, 1, 1),
    )
    assert all(t > 0 for t, _ in flows)


def test_pricing_cashflows_fallback_no_issue():
    flows = pricing_cashflows(
        nominal=1000,
        coupon_rate_pct=10,
        coupon_frequency=2,
        maturity=date(2026, 1, 1),
        asof=date(2024, 3, 1),
    )
    assert len(flows) >= 1
    assert flows[-1][1] == pytest.approx(1000 + 50)


def test_pricing_cashflows_times_positive_and_sorted():
    flows = pricing_cashflows(
        nominal=1000,
        coupon_rate_pct=10,
        coupon_frequency=4,
        maturity=date(2026, 1, 1),
        asof=date(2024, 1, 1),
        issue_date=date(2024, 1, 1),
    )
    times = [t for t, _ in flows]
    assert times == sorted(times)
    assert all(t > 0 for t in times)
