"""Comprehensive tests for scoring.explain (human-readable score explanations)."""

from __future__ import annotations

from datetime import datetime

from scoring.explain import (
    ExplainedScore,
    ScoreFactor,
    _credit_detail,
    _currency_detail,
    _duration_detail,
    _efficiency_detail,
    _yield_detail,
    explain_score,
)
from scoring.models import BondScore, ScoreBreakdown


def _score(breakdown: ScoreBreakdown | None = None, score=80.0, tier="A"):
    return BondScore(
        internal_id="B",
        score=score,
        risk_adjusted_score=score,
        breakdown=breakdown or ScoreBreakdown(),
        computed_at=datetime(2024, 1, 1),
    )


def test_score_factor_impact_classification():
    pos = ScoreFactor("yield", "Доходность", 5.0, "x")
    neg = ScoreFactor("yield", "Доходность", -5.0, "x")
    neu = ScoreFactor("yield", "Доходность", 0.0, "x")
    assert pos.impact == "positive"
    assert neg.impact == "negative"
    assert neu.impact == "neutral"
    assert pos.points == 5.0


def test_score_factor_as_dict():
    f = ScoreFactor("yield", "Доходность", 5.0, "detail").as_dict()
    assert f == {"component": "yield", "label": "Доходность", "points": 5.0,
                 "impact": "positive", "detail": "detail"}


def test_yield_detail_buckets():
    assert "Высокая" in _yield_detail(15)
    assert "Умеренная" in _yield_detail(9)
    assert "Невысокая" in _yield_detail(3)
    assert "не указана" in _yield_detail(None)


def test_currency_detail_buckets():
    assert "USD" in _currency_detail("USD")
    assert "Металл" in _currency_detail("XAU")
    assert "BYN" in _currency_detail("BYN")
    assert "EUR" in _currency_detail("EUR")


def test_duration_detail_buckets():
    assert "Короткий" in _duration_detail(20)
    assert "Средний" in _duration_detail(12)
    assert "Длинный" in _duration_detail(-15)
    assert "сбалансированный" in _duration_detail(5)


def test_credit_detail_buckets():
    assert "Государственный" in _credit_detail(15)
    assert "Повышенный" in _credit_detail(-15)
    assert "Корпоративный" in _credit_detail(-5)


def test_efficiency_detail_buckets():
    assert "Отличное" in _efficiency_detail(12)
    assert "Хорошее" in _efficiency_detail(7)
    assert "Низкая" in _efficiency_detail(1)


def test_explain_score_builds_factors_and_verdict():
    b = ScoreBreakdown(yield_component=10.0, currency_component=5.0, duration_component=-20.0)
    explained = explain_score(_score(b, tier="A"), currency="BYN", ytm_pct=10.0)
    assert isinstance(explained, ExplainedScore)
    components = {f.component for f in explained.factors}
    assert "yield" in components and "currency" in components and "duration" in components
    assert explained.verdict == "Хорошая возможность"
    # strengths come from positive, weaknesses from negative
    assert len(explained.strengths) >= 1
    assert len(explained.weaknesses) >= 1
    assert any("Длинный" in w for w in explained.weaknesses)


def test_explain_score_strengths_weaknesses_capped():
    b = ScoreBreakdown(yield_component=5, currency_component=4, duration_component=3,
                       liquidity_component=-1, credit_risk_component=-2, inflation_component=-3)
    explained = explain_score(_score(b), currency="BYN", ytm_pct=10)
    assert len(explained.strengths) <= 3
    assert len(explained.weaknesses) <= 3


def test_explain_score_factors_sorted_by_abs_points():
    b = ScoreBreakdown(yield_component=1.0, duration_component=-50.0, currency_component=3.0)
    explained = explain_score(_score(b), currency="BYN", ytm_pct=10)
    pts = [f.points for f in explained.factors]
    assert abs(pts[0]) >= abs(pts[-1])


def test_explain_score_disclaimer_present():
    explained = explain_score(_score(), currency="BYN", ytm_pct=10)
    assert "индивидуальной" in explained.disclaimer
    assert "индивидуальной" in explained.as_dict()["disclaimer"]


def test_explain_score_low_tier_verdict_avoid():
    b = ScoreBreakdown(yield_component=-10, credit_risk_component=-20)
    explained = explain_score(_score(b, score=20, tier="D"), currency="BYN", ytm_pct=2)
    assert "избегать" in explained.verdict
