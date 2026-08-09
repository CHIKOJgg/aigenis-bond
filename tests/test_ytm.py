"""Pure-math tests for the shared YTM helpers (desk.ytm)."""

from __future__ import annotations

from datetime import date

from desk.ytm import sane_yield, to_price_pct, ytm_from_price


def test_ytm_par_bond_equals_coupon():
    y = ytm_from_price(100.0, 10.0, 2, date(2036, 8, 8), asof=date(2026, 8, 8))
    assert y is not None
    assert abs(y - 10.0) < 1e-6


def test_ytm_above_coupon_for_below_par():
    # 5% annual coupon, 5y left, price 95 -> YTM ~6.21%
    y = ytm_from_price(95.0, 5.0, 1, date(2031, 8, 8), asof=date(2026, 8, 8))
    assert y is not None
    assert 6.1 < y < 6.3


def test_ytm_semiannual_five_year_keeps_all_periods():
    # Regression: (maturity-asof).days/365.25 = 4.9993 -> int() used to drop
    # the final period and overstate YTM (~6.46% instead of ~6.21%).
    y = ytm_from_price(95.0, 5.0, 2, date(2031, 8, 8), asof=date(2026, 8, 8))
    assert y is not None
    assert abs(y - 6.21) < 0.1


def test_ytm_zero_coupon_matches_compound():
    y = ytm_from_price(85.0, 0.0, 1, date(2029, 8, 8), asof=date(2026, 8, 8))
    expected = ((100 / 85) ** (1 / 3) - 1) * 100
    assert y is not None
    assert abs(y - expected) < 0.05


def test_ytm_guards_bad_inputs():
    assert ytm_from_price(0.0, 10.0, 2, date(2030, 1, 1)) is None
    assert ytm_from_price(-5.0, 10.0, 2, date(2030, 1, 1)) is None
    assert ytm_from_price(100.0, 10.0, 2, date(2020, 1, 1)) is None
    assert ytm_from_price(100.0, 10.0, 0, date(2030, 1, 1)) is None


def test_to_price_pct_normalization():
    assert abs((to_price_pct(10039.58, 10000.0) or 0) - 100.3958) < 1e-6
    assert abs((to_price_pct(99.5, 1000.0) or 0) - 99.5) < 1e-9
    assert to_price_pct(None, 1000.0) is None
    assert to_price_pct(0, 1000.0) is None


def test_to_price_pct_passes_through_percent_on_small_nominal():
    # Regression: BCSE quotes percent-of-face (100.0 = par) even for
    # 200-nominal issues. The old absolute-units window (0.5x-500x of
    # nominal) corrupted these: price 100.0 on nominal 200 became 50% and a
    # par-priced Минфин bond showed a fake 39% YTM.
    assert abs((to_price_pct(100.0, 200.0) or 0) - 100.0) < 1e-9
    assert abs((to_price_pct(100.0, 100.0) or 0) - 100.0) < 1e-9
    assert abs((to_price_pct(100.0, 50.0) or 0) - 100.0) < 1e-9
    assert abs((to_price_pct(93.39, 1000.0) or 0) - 93.39) < 1e-9


def test_to_price_pct_converts_unambiguous_absolute():
    # A 2938.6-BYН quote on a 1000-nominal USD bond cannot be a percent, so
    # it still gets converted (raw absolute leak from ingestion).
    assert abs((to_price_pct(2938.6, 1000.0) or 0) - 293.86) < 1e-9


def test_sane_yield_rejects_garbage_and_missing_estimate():
    assert not sane_yield(None, 10.0)
    assert not sane_yield(1374.0, 10.0)
    assert not sane_yield(-5.0, 10.0)
    assert not sane_yield(10.0, None)
    assert sane_yield(10.2, 10.0)
    assert not sane_yield(40.0, 10.0)
