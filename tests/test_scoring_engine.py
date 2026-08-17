"""Comprehensive tests for scoring.engine (Reward/Risk Score v4 math)."""

from __future__ import annotations

from datetime import date

from scoring.engine import (
    _classify_issuer,
    _compute_efficiency_ratio,
    _coupon_component,
    _credit_risk_component,
    _currency_component,
    _duration_component,
    _historical_volatility_component,
    _inflation_component,
    _liquidity_component,
    _metal_component,
    _peer_relative_component,
    _volatility_component,
    _yield_component,
    score_bond,
)
from scoring.models import ScoreBreakdown


def test_currency_component_table():
    assert _currency_component("USD") == 18.0
    assert _currency_component("BYN") == 14.0
    assert _currency_component("EUR") == 12.0
    assert _currency_component("ZZZ") == 10.0  # unknown fallback


def test_yield_component_linear_then_log():
    assert _yield_component(10.0) == 10.0
    assert _yield_component(0) == 0.0
    assert _yield_component(None) == 0.0
    # >40 uses diminishing log bonus (capped near 40 + small)
    assert _yield_component(100.0) < 50.0


def test_coupon_component_zero_penalty():
    assert _coupon_component(0.0, 10.0) == -3.0
    assert _coupon_component(None, 10.0) == 0.0
    assert _coupon_component(12.0, 10.0) > 6.0  # bonus for high coupon vs ytm


def test_duration_component_short_bonus_long_penalty():
    assert _duration_component(0.3) == 8.0       # very short
    assert _duration_component(10.0) < 0.0       # very long -> negative


def test_metal_component_direct_and_keyword():
    assert _metal_component("XAU") == 5.0
    # issuer containing "золото" matches the direct gold keyword -> 5.0
    assert _metal_component("BYN", issuer="Полюс Золото") == 5.0
    assert _metal_component("BYN") == 0.0


def test_liquidity_component_active_with_price():
    full = _liquidity_component(has_price=True, status="active",
                                days_to_maturity=200, price_pct=100.0)
    assert full >= 9.0  # 5 + 2 + 4 + 3 (short)
    no_price = _liquidity_component(has_price=False, status="active",
                                     days_to_maturity=200)
    assert no_price < full


def test_credit_risk_government_vs_corp():
    assert _credit_risk_component("Министерство финансов", "active") == 12.0
    assert _credit_risk_component("ООО Рога", "active") < 0.0
    assert _credit_risk_component(None, "defaulted") == -35.0


def test_classify_issuer_tiers():
    assert _classify_issuer("Министерство финансов") == "sovereign"
    assert _classify_issuer("Сбер") == "bank_systemic"
    assert _classify_issuer("ООО Рога") == "corp"
    assert _classify_issuer(None) == "unknown"


def test_inflation_component_usd_byn():
    assert _inflation_component("USD", 12.0) == 6.0
    assert _inflation_component("BYN", 15.0) == 4.0
    assert _inflation_component("BYN", 3.0) == -7.0


def test_volatility_component_extreme_ytm_penalty():
    assert _volatility_component(ytm_pct=80, price_pct=100, status="active", coupon_pct=5) < 0
    assert _volatility_component(ytm_pct=80, price_pct=100, status="defaulted", coupon_pct=5) < -5


def test_historical_volatility_component_buckets():
    assert _historical_volatility_component([10.0, 10.1, 10.0]) == 5.0  # very stable
    assert _historical_volatility_component([10.0, 20.0, 5.0]) < 0       # very unstable
    assert _historical_volatility_component([10.0]) == 0.0              # too few


def test_peer_relative_component_zscore():
    # ytm far above peers -> positive bonus
    assert _peer_relative_component(20.0, "BYN", [8, 9, 10, 11, 12, 13]) > 0
    # ytm far below peers -> negative
    assert _peer_relative_component(2.0, "BYN", [8, 9, 10, 11, 12, 13]) < 0
    # <5 peers -> no peer signal
    assert _peer_relative_component(20.0, "BYN", [8, 9]) == 0.0


def test_efficiency_ratio_bounded():
    bd = ScoreBreakdown(yield_component=10, currency_component=14, duration_component=5)
    ratio = _compute_efficiency_ratio(bd)
    assert 0.0 <= ratio <= 15.0
    # no reward -> zero
    empty = ScoreBreakdown()
    assert _compute_efficiency_ratio(empty) == 0.0


def test_score_bond_invariants():
    sc = score_bond(
        internal_id="B",
        yield_to_maturity=12.0,
        currency="BYN",
        maturity_date=date(2028, 1, 1),
        status="active",
        issuer="ООО Рога",
        coupon_rate=12.0,
        price=100.0,
    )
    bd = sc.breakdown
    # reward_subtotal = sum of non-negative components
    manual_reward = sum(
        max(v, 0.0) for v in [
            bd.yield_component, bd.currency_component, bd.duration_component,
            bd.liquidity_component, bd.metal_component, bd.credit_risk_component,
            bd.inflation_component, bd.coupon_component, bd.historical_volatility_component,
            bd.peer_relative_component,
        ]
    )
    manual_risk = sum(
        abs(min(v, 0.0)) for v in [
            bd.yield_component, bd.currency_component, bd.duration_component,
            bd.liquidity_component, bd.metal_component, bd.credit_risk_component,
            bd.inflation_component, bd.coupon_component, bd.volatility_component,
            bd.historical_volatility_component, bd.peer_relative_component,
        ]
    )
    assert bd.reward_subtotal == pytest.approx(round(manual_reward, 2), abs=0.01)
    assert bd.risk_subtotal == pytest.approx(round(manual_risk, 2), abs=0.01)
    assert bd.reward_subtotal >= 0
    assert bd.risk_subtotal >= 0
    # efficiency ratio is the engine's own computation
    assert bd.efficiency_ratio == pytest.approx(_compute_efficiency_ratio(bd), abs=0.01)
    # raw score equals sum of all 11 components
    assert sc.score == pytest.approx(bd.total(), abs=0.01)


def test_score_bond_derives_ytm_from_price_when_missing():
    sc = score_bond(
        internal_id="PX",
        yield_to_maturity=None,
        currency="BYN",
        maturity_date=date(2029, 1, 1),
        status="active",
        coupon_rate=10.0,
        price=100.0,
    )
    # par bond (price 100, coupon 10) -> ytm resolved to ~10
    assert sc.breakdown.yield_component == pytest.approx(10.0, abs=1.0)


def test_score_bond_distressed_cap():
    sc = score_bond(
        internal_id="D",
        yield_to_maturity=80.0,
        currency="BYN",
        maturity_date=date(2028, 1, 1),
        status="active",
        coupon_rate=5.0,
        price=50.0,  # <70% and ytm>40 -> distressed
    )
    # distressed reward capped, extra volatility penalty applied
    assert sc.breakdown.yield_component <= 20.0
    assert sc.breakdown.volatility_component < 0


def test_score_bond_metal_no_coupon_strips_stored_yield():
    # Металлическая бескупонная бумага: даже хранимые 12% не дают доходности —
    # ни напрямую, ни через решение из цены/дефолта по валюте.
    for currency, indexation in (("XAU", None), (None, "XAG"), ("XPT", None)):
        sc = score_bond(
            internal_id="M",
            yield_to_maturity=12.0,
            currency=currency or "BYN",
            maturity_date=date(2029, 1, 1),
            status="active",
            coupon_rate=0.001,
            price=90.0,  # discount would otherwise yield ~5% via zero-coupon solve
            indexation_currency=indexation,
        )
        assert sc.breakdown.yield_component == 0.0


def test_score_bond_metal_with_real_coupon_keeps_yield():
    sc = score_bond(
        internal_id="M2",
        yield_to_maturity=12.0,
        currency="XAU",
        maturity_date=date(2029, 1, 1),
        status="active",
        coupon_rate=3.0,
        price=100.0,
    )
    assert sc.breakdown.yield_component == pytest.approx(12.0, abs=0.5)


import pytest  # noqa: E402
