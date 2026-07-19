"""Unit tests for scoring models + explanation (scoring/models, scoring/explain)."""
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
    )
    assert bd.total() == 85.0


def test_bond_score_tier_boundaries():
    def score(v: float) -> str:
        return BondScore(
            internal_id="x",
            score=v,
            breakdown=ScoreBreakdown(),
            computed_at=datetime.now(),
        ).tier

    assert score(95) == "S"
    assert score(90) == "S"
    assert score(89.9) == "A"
    assert score(80) == "A"
    assert score(70) == "B"
    assert score(60) == "C"
    assert score(59.9) == "D"
    assert score(0) == "D"
    assert score(-100) == "D"


def test_explained_score_structure_and_disclaimer():
    s = score_bond(
        internal_id="OP-1",
        yield_to_maturity=12.0,
        currency="USD",
        maturity_date=datetime(2030, 1, 1).date(),
        status="active",
        issuer="Treasury",
        price=100.0,
    )
    explained = explain_score(s, currency="USD", ytm_pct=12.0)
    assert isinstance(explained, ExplainedScore)
    assert explained.score == round(s.score, 2)
    assert explained.tier == s.tier
    assert explained.verdict  # non-empty verdict text
    assert explained.summary
    d = explained.as_dict()
    assert d["disclaimer"]  # disclaimer always attached
    assert all(f.impact in ("positive", "negative", "neutral") for f in explained.factors)
    # Factors sorted by absolute impact descending.
    impacts = [abs(f.points) for f in explained.factors]
    assert impacts == sorted(impacts, reverse=True)


def test_explained_score_strengths_weaknesses():
    s = score_bond(
        internal_id="L",
        yield_to_maturity=1.0,
        currency="EUR",
        maturity_date=datetime(2035, 1, 1).date(),
        status="active",
        issuer="Some Corp",
        price=100.0,
    )
    explained = explain_score(s, currency="EUR", ytm_pct=1.0)
    # Low score -> weaknesses present, strengths may be empty but attributes exist.
    assert isinstance(explained.strengths, list)
    assert isinstance(explained.weaknesses, list)
    assert explained.tier == "D"


def test_score_factor_impact_sign():
    pos = ScoreFactor("yield", "Доходность", 10.0, "high")
    neg = ScoreFactor("duration", "Срок", -15.0, "long")
    neu = ScoreFactor("x", "y", 0.0, "z")
    assert pos.impact == "positive"
    assert neg.impact == "negative"
    assert neu.impact == "neutral"
    assert pos.points == 10.0


def test_user_preferences_validation_bounds():
    # Shares must be within [0, 1].
    import pytest

    with pytest.raises(Exception):
        UserPreferences(
            user_id=1,
            share_usd=1.5,  # out of range
            share_byn=0.3,
            share_metals=0.1,
            share_eur=0.1,
        )
