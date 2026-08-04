"""Tests for scoring v4 — new features: historical volatility, peer-relative, risk-adjusted."""
from __future__ import annotations

from datetime import date

import pytest

from scoring.engine import (
    _compute_efficiency_ratio,
    _historical_volatility_component,
    _peer_relative_component,
    score_bond,
)
from scoring.models import ScoreBreakdown


class TestHistoricalVolatility:
    def test_none_returns_zero(self):
        assert _historical_volatility_component(None) == 0.0

    def test_too_few_points(self):
        assert _historical_volatility_component([10.0]) == 0.0
        assert _historical_volatility_component([10.0, 11.0]) == 0.0

    def test_stable_ytm_bonus(self):
        assert _historical_volatility_component([10.0, 10.1, 10.0, 10.2, 9.9]) == 5.0

    def test_moderate_volatility(self):
        assert _historical_volatility_component([10.0, 11.0, 9.0, 12.0, 8.0]) == 1.0

    def test_high_volatility_penalty(self):
        s = _historical_volatility_component([10.0, 20.0, 5.0, 25.0, 0.0, 30.0])
        assert s < 0

    def test_extreme_volatility(self):
        s = _historical_volatility_component([10.0, 50.0, 5.0, 60.0, 0.0])
        assert s == -4.0

    def test_negative_ytms_filtered(self):
        s = _historical_volatility_component([10.0, -5.0, 11.0, -3.0, 10.5])
        assert s >= 1.0  # clean values have low stdev


class TestPeerRelative:
    def test_none_returns_zero(self):
        assert _peer_relative_component(None, "USD", None) == 0.0
        assert _peer_relative_component(10.0, "USD", None) == 0.0

    def test_too_few_peers(self):
        assert _peer_relative_component(10.0, "USD", [1.0, 2.0, 3.0]) == 0.0

    def test_well_above_peers(self):
        peers = [8.0, 9.0, 8.5, 9.5, 10.0, 8.0, 9.0, 8.5, 9.5, 10.0]
        s = _peer_relative_component(14.0, "USD", peers)
        assert s >= 3.0

    def test_above_peers(self):
        peers = [8.0, 9.0, 8.5, 9.5, 10.0, 8.0, 9.0, 8.5, 9.5, 10.0]
        s = _peer_relative_component(10.0, "USD", peers)
        assert s >= 0

    def test_below_peers(self):
        peers = [10.0, 11.0, 10.5, 11.5, 12.0, 10.0, 11.0, 10.5, 11.5, 12.0]
        s = _peer_relative_component(6.0, "USD", peers)
        assert s < 0

    def test_near_average(self):
        peers = [10.0, 11.0, 9.0, 10.5, 9.5, 10.0, 11.0, 10.5, 9.0, 10.0]
        s = _peer_relative_component(10.0, "USD", peers)
        assert -1 <= s <= 3


class TestEfficiencyRatio:
    def test_good_bond_efficiency(self):
        bd = ScoreBreakdown(
            yield_component=15, currency_component=20, duration_component=7,
            liquidity_component=11, credit_risk_component=12, inflation_component=6,
            coupon_component=4, historical_volatility_component=3,
            volatility_component=0,
        )
        ratio = _compute_efficiency_ratio(bd)
        assert ratio > 5

    def test_risky_bond_low_efficiency(self):
        bd = ScoreBreakdown(
            yield_component=3, currency_component=0, duration_component=-3,
            liquidity_component=0, credit_risk_component=-28, inflation_component=-2,
            volatility_component=-5,
        )
        ratio = _compute_efficiency_ratio(bd)
        assert ratio < 1.5

    def test_no_risk_max_efficiency(self):
        bd = ScoreBreakdown(
            yield_component=20, currency_component=20, duration_component=8,
            liquidity_component=11, credit_risk_component=12, inflation_component=6,
            coupon_component=4,
        )
        ratio = _compute_efficiency_ratio(bd)
        assert ratio > 10


class TestScoreBondV4:
    def test_has_risk_adjusted_score(self):
        s = score_bond(
            internal_id="V4",
            yield_to_maturity=12.0,
            currency="USD",
            maturity_date=date(2030, 1, 1),
            status="active",
            issuer="Treasury",
            price=100.0,
            nominal=100.0,
            coupon_rate=8.0,
        )
        assert s.risk_adjusted_score > 0
        assert s.breakdown.reward_subtotal > 0
        assert s.breakdown.efficiency_ratio > 0

    def test_historical_data_improves_score(self):
        base = score_bond(
            internal_id="HIST", yield_to_maturity=12.0, currency="USD",
            maturity_date=date(2030, 1, 1), status="active", issuer="Treasury",
            price=100.0, nominal=100.0, coupon_rate=8.0,
        )
        with_history = score_bond(
            internal_id="HIST", yield_to_maturity=12.0, currency="USD",
            maturity_date=date(2030, 1, 1), status="active", issuer="Treasury",
            price=100.0, nominal=100.0, coupon_rate=8.0,
            ytm_history=[12.0, 12.1, 11.9, 12.0, 12.2, 11.8, 12.1, 12.0],
        )
        assert with_history.score >= base.score

    def test_unstable_history_penalizes(self):
        base = score_bond(
            internal_id="UNST", yield_to_maturity=12.0, currency="USD",
            maturity_date=date(2030, 1, 1), status="active", issuer="Treasury",
            price=100.0, nominal=100.0, coupon_rate=8.0,
        )
        with_bad_history = score_bond(
            internal_id="UNST", yield_to_maturity=12.0, currency="USD",
            maturity_date=date(2030, 1, 1), status="active", issuer="Treasury",
            price=100.0, nominal=100.0, coupon_rate=8.0,
            ytm_history=[12.0, 30.0, 5.0, 25.0, 8.0, 20.0],
        )
        assert with_bad_history.score < base.score

    def test_above_peers_improves_score(self):
        peers = [8.0, 9.0, 8.5, 9.5, 10.0, 8.0, 9.0, 8.5, 9.5, 10.0]
        base = score_bond(
            internal_id="PEER", yield_to_maturity=10.0, currency="USD",
            maturity_date=date(2030, 1, 1), status="active", issuer="Treasury",
            price=100.0, nominal=100.0, coupon_rate=6.0,
        )
        above = score_bond(
            internal_id="PEER", yield_to_maturity=15.0, currency="USD",
            maturity_date=date(2030, 1, 1), status="active", issuer="Treasury",
            price=100.0, nominal=100.0, coupon_rate=6.0,
            peer_ytms=peers,
        )
        assert above.breakdown.peer_relative_component > 0
        assert above.score > base.score

    def test_breakdown_total_excludes_meta(self):
        s = score_bond(
            internal_id="META", yield_to_maturity=15.0, currency="USD",
            maturity_date=date(2030, 1, 1), status="active", issuer="Treasury",
            price=100.0, nominal=100.0, coupon_rate=8.0,
        )
        bd = s.breakdown
        core = sum([
            bd.yield_component, bd.currency_component, bd.duration_component,
            bd.liquidity_component, bd.metal_component, bd.credit_risk_component,
            bd.inflation_component, bd.coupon_component, bd.volatility_component,
            bd.historical_volatility_component, bd.peer_relative_component,
        ])
        assert round(core, 2) == bd.total()
        assert bd.total() == s.score
        assert bd.reward_subtotal > 0
        assert bd.efficiency_ratio > 0
