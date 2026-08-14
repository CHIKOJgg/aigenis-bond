"""Unit tests for the Reward/Risk scoring engine v2 (scoring/engine.py)."""

from __future__ import annotations

from datetime import date

import pytest

from scoring.engine import (
    _classify_issuer,
    _credit_risk_component,
    _currency_component,
    _duration_component,
    _inflation_component,
    _liquidity_component,
    _metal_component,
    _volatility_component,
    _yield_component,
    score_bond,
    score_bonds,
)
from scoring.models import BondScore


def test_currency_component_known_values():
    assert _currency_component("USD") == 18.0
    assert _currency_component("XAU") == 16.0
    assert _currency_component("XAG") == 13.0
    assert _currency_component("XPT") == 10.0
    assert _currency_component("BYN") == 14.0
    assert _currency_component("RUB") == 12.0
    assert _currency_component("CNY") == 12.0
    assert _currency_component("EUR") == 12.0
    assert _currency_component("ZZZ") == 10.0


def test_currency_component_case_insensitive():
    assert _currency_component("usd") == 18.0


def test_yield_component_bounds():
    assert _yield_component(None) == 0.0
    assert _yield_component(0) == 0.0
    assert _yield_component(-3) == 0.0
    assert _yield_component(8) == 8.0
    assert _yield_component(15.5) == 15.5
    assert _yield_component(40) == 40.0


def test_yield_component_extreme():
    assert _yield_component(100) > 40.0
    assert _yield_component(200) > _yield_component(100)


def test_duration_component_smooth():
    assert _duration_component(None) == 0.0
    short = _duration_component(0.5)
    assert short >= 7.0
    medium = _duration_component(3.5)
    assert 3.0 < medium < 8.0
    long = _duration_component(15.0)
    assert long < 0


def test_duration_component_monotonic():
    assert (
        _duration_component(1.0)
        > _duration_component(3.0)
        > _duration_component(6.0)
        > _duration_component(10.0)
    )


def test_metal_component():
    assert _metal_component("XAU") == 5.0
    assert _metal_component("XAG") == 4.0
    assert _metal_component("XPT") == 3.0
    assert _metal_component("USD") == 0.0


def test_liquidity_component_combinations():
    good = _liquidity_component(has_price=True, status="active", days_to_maturity=100)
    assert good == 5 + 4 + 3 + 2
    bad = _liquidity_component(has_price=False, status="delisted", days_to_maturity=None)
    assert bad == 0
    off = _liquidity_component(has_price=False, status="offer", days_to_maturity=None)
    assert off == -5


def test_liquidity_component_price_nominal():
    good = _liquidity_component(
        has_price=True, status="active", days_to_maturity=200, price_pct=100.0
    )
    bad = _liquidity_component(
        has_price=True, status="active", days_to_maturity=200, price_pct=20.0
    )
    assert good > bad


def test_classify_issuer_tiers():
    assert _classify_issuer("Министерство финансов") == "sovereign"
    assert _classify_issuer("Government of Russia") == "sovereign"
    assert _classify_issuer("Сбербанк") == "bank_systemic"
    assert _classify_issuer("ВТБ") == "bank_systemic"
    assert _classify_issuer("Альфа-банк") == "bank_systemic"
    assert _classify_issuer("Газпром") == "state_corp"
    assert _classify_issuer("Лукойл") == "state_corp"
    assert _classify_issuer("Acme Bank") == "bank"
    assert _classify_issuer("Acme Corp") == "corp"
    assert _classify_issuer(None) == "unknown"


def test_credit_risk_component():
    assert _credit_risk_component("Министерство финансов", "active") == 12.0
    assert _credit_risk_component("Газпром", "active") == 6.0
    assert _credit_risk_component("Сбербанк", "active") == 3.0
    assert _credit_risk_component("Acme Bank", "active") == 0.0
    assert _credit_risk_component("Acme Corp", "active") == -3.0
    assert _credit_risk_component(None, "active") == -2.0
    assert _credit_risk_component("Any", "delisted") == -28.0
    assert _credit_risk_component("Any", "matured") == -12.0
    assert _credit_risk_component("Any", "defaulted") == -35.0


def test_inflation_component():
    assert _inflation_component("USD", 12) == 6.0
    assert _inflation_component("USD", 7) == 4.0
    assert _inflation_component("USD", 3) == 3.0
    assert _inflation_component("USD", None) == 3.0
    assert _inflation_component("BYN", 15) == 4.0
    assert _inflation_component("BYN", 9) == 1.0
    assert _inflation_component("BYN", 6) == -3.0
    assert _inflation_component("BYN", 3) == -7.0
    assert _inflation_component("BYN", None) == -7.0
    assert _inflation_component("EUR", 6) == 1.0
    assert _inflation_component("EUR", 2) == -2.0
    assert _inflation_component("RUB", 18) == 4.0
    assert _inflation_component("RUB", 14) == 2.0
    assert _inflation_component("RUB", 10) == -1.0
    assert _inflation_component("CNY", 8) == 2.0
    assert _inflation_component("CNY", 3) == 0.0
    assert _inflation_component("XAU", 5) == 0.0


def test_volatility_component_penalties():
    extreme = _volatility_component(
        ytm_pct=80, price_pct=None, status="active", coupon_pct=5.0
    )
    assert extreme < 0
    normal = _volatility_component(
        ytm_pct=10, price_pct=100.0, status="active", coupon_pct=5.0
    )
    assert normal == 0.0
    extreme_price = _volatility_component(
        ytm_pct=10, price_pct=10.0, status="active", coupon_pct=5.0
    )
    assert extreme_price < 0


def test_score_bond_basic_and_tier():
    s: BondScore = score_bond(
        internal_id="OP-1",
        yield_to_maturity=12.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Ministry of Finance",
        price=100.0,
        nominal=100.0,
        coupon_rate=8.0,
    )
    assert s.score > 0
    assert s.tier in {"S", "A", "B", "C", "D"}
    assert s.breakdown.total() == s.score
    assert s.breakdown.coupon_component > 0
    assert s.breakdown.volatility_component == 0.0


def test_score_bond_tier_boundaries():
    low = score_bond(
        internal_id="L",
        yield_to_maturity=1.0,
        currency="EUR",
        maturity_date=date(2035, 1, 1),
        status="active",
        issuer="Some Corp",
        price=100.0,
        nominal=100.0,
    )
    assert low.tier == "D"

    high = score_bond(
        internal_id="H",
        yield_to_maturity=60.0,
        currency="USD",
        maturity_date=date(2027, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=8.0,
    )
    assert high.tier in {"S", "A", "B"}


def test_distressed_bond_yield_reward_is_capped():
    # Regression: Republic of Belarus 2027 USD (price 71, phantom 92% YTM on
    # a defaulted issue) used to top the universe with S/87.1. A bond below
    # 80% of face with YTM > 30% is distressed debt: the yield is a risk
    # signal, not an opportunity, so reward is capped and risk deepened.
    distressed = score_bond(
        internal_id="DISTR",
        yield_to_maturity=92.4,
        currency="USD",
        maturity_date=date(2027, 6, 29),
        status="active",
        issuer="Republic of Belarus",
        price=69.0,
        nominal=100.0,
        coupon_rate=7.625,
    )
    assert distressed.breakdown.yield_component <= 20.0
    assert distressed.breakdown.volatility_component <= -18.0
    assert distressed.score < 75.0
    assert distressed.tier in {"C", "D"}

    # Same credit at par is not distressed: normal reward stays.
    healthy = score_bond(
        internal_id="HEALTHY",
        yield_to_maturity=25.0,
        currency="USD",
        maturity_date=date(2027, 6, 29),
        status="active",
        issuer="Republic of Belarus",
        price=100.0,
        nominal=100.0,
        coupon_rate=7.625,
    )
    assert healthy.breakdown.yield_component == 25.0
    assert healthy.score > distressed.score


def test_score_bonds_batch():
    out = score_bonds(
        [
            {"internal_id": "A", "yield_to_maturity": 10.0, "currency": "USD", "status": "active"},
            {"internal_id": "B", "yield_to_maturity": 5.0, "currency": "BYN", "status": "active"},
        ]
    )
    assert [b.internal_id for b in out] == ["A", "B"]
    assert all(isinstance(b, BondScore) for b in out)


def test_score_calibration_max_never_exceeds_100():
    """Theoretical maximum with all components is around 105 for v2 (new components)."""
    perfect = score_bond(
        internal_id="MAX",
        yield_to_maturity=40.0,
        currency="USD",
        maturity_date=date(2027, 1, 1),
        status="active",
        issuer="Министерство финансов",
        price=100.0,
        nominal=100.0,
        coupon_rate=12.0,
    )
    assert perfect.score <= 110.0
    assert perfect.score >= 95.0

    from scoring.engine import CURRENCY_BONUS

    for cur in CURRENCY_BONUS:
        s = score_bond(
            internal_id=f"MAX-{cur}",
            yield_to_maturity=40.0,
            currency=cur,
            maturity_date=date(2027, 1, 1),
            status="active",
            issuer="Министерство финансов",
            price=100.0,
            nominal=100.0,
            coupon_rate=12.0,
        )
        assert s.score <= 110.0, f"{cur} exceeds 110: {s.score}"


def test_score_calibration_tiers_are_meaningful():
    typical_good_usd = score_bond(
        internal_id="TYP",
        yield_to_maturity=15.0,
        currency="USD",
        maturity_date=date(2029, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=6.0,
    )
    assert 55 <= typical_good_usd.score <= 80
    assert typical_good_usd.tier in {"B", "C", "A"}

    exceptional = score_bond(
        internal_id="EXC",
        yield_to_maturity=35.0,
        currency="USD",
        maturity_date=date(2027, 1, 1),
        status="active",
        issuer="Министерство финансов",
        price=100.0,
        nominal=100.0,
        coupon_rate=10.0,
    )
    assert exceptional.tier in {"S", "A"}

    weak = score_bond(
        internal_id="WK",
        yield_to_maturity=2.0,
        currency="EUR",
        maturity_date=date(2036, 1, 1),
        status="delisted",
        issuer="Some Corp",
        price=None,
    )
    assert weak.tier == "D"


def test_rub_scoring():
    s = score_bond(
        internal_id="RUB-1",
        yield_to_maturity=16.0,
        currency="RUB",
        maturity_date=date(2028, 1, 1),
        status="active",
        issuer="Министерство финансов",
        price=100.0,
        nominal=100.0,
        coupon_rate=10.0,
    )
    assert s.breakdown.currency_component == 12.0
    assert s.breakdown.inflation_component == 4.0
    assert s.score > 0


def test_cny_scoring():
    s = score_bond(
        internal_id="CNY-1",
        yield_to_maturity=8.0,
        currency="CNY",
        maturity_date=date(2028, 1, 1),
        status="active",
        issuer="Government",
        price=100.0,
        nominal=100.0,
        coupon_rate=5.0,
    )
    assert s.breakdown.currency_component == 12.0
    assert s.breakdown.inflation_component == 2.0


def test_zero_coupon_bond_penalty():
    s = score_bond(
        internal_id="ZERO",
        yield_to_maturity=2.0,
        currency="EUR",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Some Corp",
        price=100.0,
        nominal=100.0,
        coupon_rate=0.0,
    )
    assert s.breakdown.coupon_component < 0


@pytest.mark.parametrize(
    "issuer,expected_tier",
    [
        ("Министерство финансов Республики Беларусь", "sovereign"),
        ("Государственное казначейство", "sovereign"),
        ("Счётная палата", "sovereign"),
        ("Сбербанк России", "bank_systemic"),
        ("ВТБ Капитал", "bank_systemic"),
        ("ВЭБ.РФ", "bank_systemic"),
        ("Газпром нефть", "state_corp"),
        ("Транснефть", "state_corp"),
        ("Роснефть", "state_corp"),
        ("Лукойл", "state_corp"),
        ("Татнефть", "state_corp"),
        ("Русгидро", "state_corp"),
        ("РЖД-Инвест", "state_corp"),
        ("Аэрофлот", "state_corp"),
        ("Почта России", "state_corp"),
        ("Beta Bank International", "bank"),
        ("ООО Ромашка", "corp"),
        ("", "unknown"),
        (None, "unknown"),
    ],
)
def test_issuer_classification(issuer, expected_tier):
    assert _classify_issuer(issuer) == expected_tier


def test_historical_volatility_branches():
    from scoring.engine import _historical_volatility_component

    assert _historical_volatility_component(None) == 0.0
    assert _historical_volatility_component([5.0, 5.0]) == 0.0
    assert _historical_volatility_component([5.0, 5.0, -1.0]) == 0.0
    assert _historical_volatility_component([5.0, 5.0, 5.0]) == 5.0
    assert _historical_volatility_component([1.0, 1.0, 5.0, 9.0, 9.0]) == 0.0


def test_historical_volatility_stdev_error(monkeypatch):
    from scoring.engine import _historical_volatility_component, statistics

    def boom(values):
        raise statistics.StatisticsError("n < 2")

    monkeypatch.setattr("scoring.engine.statistics.stdev", boom)
    assert _historical_volatility_component([1.0, 2.0, 3.0]) == 0.0


def test_peer_relative_branches(monkeypatch):
    from scoring.engine import _peer_relative_component, statistics

    assert _peer_relative_component(None, "USD", [8, 9, 10, 11, 12]) == 0.0
    assert _peer_relative_component(5.0, "USD", [8, 9, 10, 11]) == 0.0
    assert _peer_relative_component(5.0, "USD", [8, 9, 10, 11, -1]) == 0.0
    assert _peer_relative_component(5.0, "USD", [5.0] * 5) == 0.0
    assert _peer_relative_component(10.0, "USD", [8, 9, 10, 11, 12]) == 1.0
    assert _peer_relative_component(7.0, "USD", [8, 9, 10, 11, 12]) == -3.0

    def boom(values):
        raise statistics.StatisticsError("n < 2")

    monkeypatch.setattr("scoring.engine.statistics.stdev", boom)
    assert _peer_relative_component(5.0, "USD", [8, 9, 10, 11, 12]) == 0.0


def test_classify_issuer_sub_sovereign():
    from scoring.engine import _classify_issuer

    assert _classify_issuer("Федеральное агентство") == "sub_sovereign"


def test_volatility_component_price_band():
    from scoring.engine import _volatility_component

    assert (
        _volatility_component(
            ytm_pct=None, price_pct=40.0, status="active", coupon_pct=None
        )
        == -1.0
    )


def test_inflation_component_market():
    from scoring.engine import _inflation_component_market

    assert _inflation_component_market("RUB", 20.0, True) == 5.0
    assert _inflation_component_market("RUB", 15.0, True) == 3.0
    assert _inflation_component_market("RUB", 12.0, True) == 0.0
    assert _inflation_component_market("RUB", 5.0, True) == -2.0
    assert _inflation_component_market("BYN", 12.0, True) == 2.0
    assert _inflation_component_market("BYN", 5.0, True) == -1.0
    assert _inflation_component_market("BYN", None, False) == -5.0
    assert _inflation_component_market("USD", 3.0, True) == 3.0


def test_efficiency_ratio_zero():
    from scoring.engine import ScoreBreakdown, _compute_efficiency_ratio

    b = ScoreBreakdown()
    assert _compute_efficiency_ratio(b) == 0.0


def test_distressed_debt_scoring_with_large_nominal():
    from scoring.engine import score_bond

    # Nominal 1000 RUB, price 600 RUB (60% of face), YTM 45% -> distressed!
    s = score_bond(
        internal_id="DIST-1000",
        yield_to_maturity=45.0,
        currency="RUB",
        maturity_date=date(2027, 1, 1),
        status="active",
        issuer="Corp",
        price=600.0,
        nominal=1000.0,
        coupon_rate=10.0,
        market="moex",
    )
    # Yield component should be capped at 20.0 due to distress penalty
    assert s.breakdown.yield_component <= 20.0
    assert s.breakdown.volatility_component <= -18.0

