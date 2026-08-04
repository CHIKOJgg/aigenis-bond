"""Unit tests for scoring models + explanation v2 (scoring/models, scoring/explain)."""
from __future__ import annotations

from datetime import datetime

from scoring.engine import score_bond
from scoring.explain import ExplainedScore, ScoreFactor, explain_score
from scoring.models import BondScore, ScoreBreakdown, UserPreferences


def test_score_breakdown_total_sums_components():
    bd = ScoreBreakdown(
        yield_component=10,
        currency_component=25,
        duration_component=20,
        liquidity_component=5,
        metal_component=10,
        credit_risk_component=10,
        inflation_component=5,
        coupon_component=3,
        volatility_component=-2,
    )
    assert bd.total() == 86.0


def test_bond_score_tier_boundaries():
    def score(v: float) -> str:
        return BondScore(
            internal_id="x",
            score=v,
            breakdown=ScoreBreakdown(),
            computed_at=datetime.now(),
        ).tier

    assert score(95) == "S"
    assert score(85) == "S"
    assert score(84.9) == "A"
    assert score(75) == "A"
    assert score(60) == "B"
    assert score(45) == "C"
    assert score(44.9) == "D"
    assert score(0) == "D"
    assert score(-100) == "D"


def test_explained_score_structure_and_disclaimer():
    from datetime import date

    s = score_bond(
        internal_id="OP-1",
        yield_to_maturity=12.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=8.0,
    )
    explained = explain_score(s, currency="USD", ytm_pct=12.0, coupon_pct=8.0)
    assert isinstance(explained, ExplainedScore)
    assert explained.score == round(s.score, 2)
    assert explained.tier == s.tier
    assert explained.verdict
    assert explained.summary
    d = explained.as_dict()
    assert d["disclaimer"]
    assert all(f.impact in ("positive", "negative", "neutral") for f in explained.factors)
    impacts = [abs(f.points) for f in explained.factors]
    assert impacts == sorted(impacts, reverse=True)


def test_explained_score_strengths_weaknesses():
    from datetime import date

    s = score_bond(
        internal_id="L",
        yield_to_maturity=1.0,
        currency="EUR",
        maturity_date=date(2035, 1, 1),
        status="active",
        issuer="Some Corp",
        price=100.0,
        nominal=100.0,
    )
    explained = explain_score(s, currency="EUR", ytm_pct=1.0)
    assert isinstance(explained.strengths, list)
    assert isinstance(explained.weaknesses, list)
    assert explained.tier == "D"


def test_explained_score_new_components():
    from datetime import date

    s = score_bond(
        internal_id="NEW",
        yield_to_maturity=15.0,
        currency="USD",
        maturity_date=date(2028, 1, 1),
        status="active",
        issuer="Газпром",
        price=100.0,
        nominal=100.0,
        coupon_rate=12.0,
    )
    explained = explain_score(s, currency="USD", ytm_pct=15.0, coupon_pct=12.0)
    component_names = {f.component for f in explained.factors}
    assert "coupon" in component_names
    assert "volatility" in component_names or s.breakdown.volatility_component == 0.0
    assert len(explained.factors) >= 7


def test_score_factor_impact_sign():
    pos = ScoreFactor("yield", "Доходность", 10.0, "high")
    neg = ScoreFactor("duration", "Срок", -15.0, "long")
    neu = ScoreFactor("x", "y", 0.0, "z")
    assert pos.impact == "positive"
    assert neg.impact == "negative"
    assert neu.impact == "neutral"
    assert pos.points == 10.0


def test_user_preferences_validation_bounds():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        UserPreferences(
            user_id=1,
            share_usd=1.5,
            share_byn=0.3,
            share_metals=0.1,
            share_eur=0.1,
        )
