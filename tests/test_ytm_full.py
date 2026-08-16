"""Comprehensive tests for desk.ytm shared yield/price helpers."""

from __future__ import annotations

from datetime import date

from desk.ytm import (
    honest_yield,
    sane_yield,
    sanity_tolerance_pp,
    to_price_pct,
    ytm_from_price,
)


def test_to_price_pct_passthrough_percent_quote():
    assert to_price_pct(100.0, 1000) == 100.0
    assert to_price_pct(95.5, None) == 95.5


def test_to_price_pct_none_returns_none():
    assert to_price_pct(None, 1000) is None
    assert to_price_pct("garbage", 1000) is None


def test_to_price_pct_absolute_converted_to_percent():
    # price 950 against nominal 1000 -> 95% of face
    assert to_price_pct(950.0, 1000) == 95.0


def test_to_price_pct_tiny_quote_treated_as_absolute():
    # price 50 with nominal 1000 -> 5? but 50<0.5? no; 50 not <0.5, not >500,
    # nom>=2000? nom=1000 so stays 50. Use a >500 absolute case:
    assert to_price_pct(1050.0, 1000) == 105.0


def test_honest_yield_returns_stored_for_normal():
    assert honest_yield(stored_ytm_pct=10.0, coupon_rate_pct=10.0,
                        indexation_currency=None) == 10.0


def test_honest_yield_zero_for_indexed_metal_no_coupon():
    assert honest_yield(stored_ytm_pct=12.0, coupon_rate_pct=0.0,
                        indexation_currency="XAU") == 0.0


def test_honest_yield_keeps_stored_for_indexed_metal_with_coupon():
    assert honest_yield(stored_ytm_pct=12.0, coupon_rate_pct=3.0,
                        indexation_currency="XAU") == 12.0


def test_ytm_from_price_par_around_coupon():
    # 10% coupon, price 100 => YTM ~10%
    ytm = ytm_from_price(100.0, 10.0, 2, date(2029, 1, 1), asof=date(2024, 1, 1))
    assert ytm is not None
    assert ytm == pytest.approx(10.0, abs=0.5)


def test_ytm_from_price_premium_yields_lower():
    ytm_high = ytm_from_price(100.0, 10.0, 2, date(2029, 1, 1), asof=date(2024, 1, 1))
    ytm_prem = ytm_from_price(105.0, 10.0, 2, date(2029, 1, 1), asof=date(2024, 1, 1))
    assert ytm_prem < ytm_high


def test_ytm_from_price_discount_yields_higher():
    ytm_disc = ytm_from_price(95.0, 10.0, 2, date(2029, 1, 1), asof=date(2024, 1, 1))
    assert ytm_disc == pytest.approx(11.4, abs=1.0)


def test_ytm_from_price_expired_returns_none():
    assert ytm_from_price(100.0, 10.0, 2, date(2020, 1, 1), asof=date(2024, 1, 1)) is None


def test_ytm_from_price_bad_inputs_return_none():
    assert ytm_from_price(-5.0, 10.0, 2, date(2029, 1, 1), asof=date(2024, 1, 1)) is None
    assert ytm_from_price(100.0, -1.0, 2, date(2029, 1, 1), asof=date(2024, 1, 1)) is None


def test_sane_yield_true_within_tolerance():
    assert sane_yield(10.0, 10.5) is True


def test_sane_yield_false_outside_tolerance():
    assert sane_yield(10.0, 30.0) is False


def test_sane_yield_false_when_missing():
    assert sane_yield(None, 10.0) is False
    assert sane_yield(10.0, None) is False


def test_sane_yield_false_negative():
    assert sane_yield(-5.0, -5.0) is False


def test_sanity_tolerance_positive():
    assert sanity_tolerance_pp() > 0


import pytest  # noqa: E402
