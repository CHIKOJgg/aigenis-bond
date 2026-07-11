"""Unit tests for the recommendation engine (recommendations/engine.py).

The ML model inference is mocked so the test stays hermetic (no trained
artifacts required) and focuses on the gating/sorting/explanation logic.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from ml.models import Decision, Prediction
from recommendations.engine import _confidence_rank, recommend_bonds
from scoring.models import UserPreferences


def _pred(internal_id: str, decision: Decision, ret: float | None = None) -> Prediction:
    return Prediction(
        internal_id=internal_id,
        model_version="test",
        model_kind="ytm_regression",
        asof_date=date(2026, 1, 1),
        predicted_ytm=ret,
        predicted_return_pct=ret,
        decision=decision,
        confidence=0.8,
        feature_importance={},
        explanation=[f"expl {decision}"],
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def stub_predict(monkeypatch):
    """Replace predict_batch with a buy/hold/avoid oracle keyed by id suffix."""
    decisions = {"buy": "buy", "hold": "hold", "avoid": "avoid", "wait": "wait"}

    def fake(features, *, regressor_path=None, classifier_path=None):
        out = []
        for f in features:
            dec = decisions.get(f.internal_id.split("-")[-1], "hold")
            out.append(_pred(f.internal_id, dec))  # type: ignore[arg-type]
        return out

    monkeypatch.setattr("recommendations.engine.predict_batch", fake)


def test_confidence_rank_bounds():
    assert 0.0 <= _confidence_rank("buy", 0.5, 50) <= 1.0
    assert _confidence_rank("buy", 0.9, 90) > _confidence_rank("avoid", 0.1, 10)


def test_recommend_respects_watchlist_gate(stub_predict):
    bonds = [
        {"internal_id": "X-buy", "currency": "USD", "yield_to_maturity": 9.0, "status": "active"},
        {"internal_id": "X-hold", "currency": "USD", "yield_to_maturity": 9.0, "status": "active"},
    ]
    prefs = UserPreferences(user_id=1, watchlist=["X-buy"])
    out = recommend_bonds(bonds, prefs, asof=date(2026, 1, 1))
    ids = [r.internal_id for r in out]
    assert "X-buy" in ids
    assert "X-hold" not in ids  # hold + not on watchlist → dropped


def test_recommend_currency_share_gate(stub_predict):
    bonds = [
        {"internal_id": "X-buy", "currency": "USD", "yield_to_maturity": 9.0, "status": "active"},
        {"internal_id": "Y-buy", "currency": "BYN", "yield_to_maturity": 9.0, "status": "active"},
    ]
    prefs = UserPreferences(user_id=1, share_usd=0.0, share_byn=0.5)
    out = recommend_bonds(bonds, prefs, asof=date(2026, 1, 1))
    ids = [r.internal_id for r in out]
    assert "X-buy" not in ids  # USD share 0 → excluded
    assert "Y-buy" in ids


def test_recommend_sorts_by_decision_rank(stub_predict):
    bonds = [
        {"internal_id": "a-avoid", "currency": "USD", "yield_to_maturity": 9.0, "status": "active"},
        {"internal_id": "b-buy", "currency": "USD", "yield_to_maturity": 9.0, "status": "active"},
        {"internal_id": "c-hold", "currency": "USD", "yield_to_maturity": 9.0, "status": "active"},
    ]
    prefs = UserPreferences(user_id=1, watchlist=["a-avoid", "b-buy", "c-hold"])
    out = recommend_bonds(bonds, prefs, asof=date(2026, 1, 1))
    assert out[0].decision == "buy"
    # top_k default 10; ranks assigned sequentially.
    assert out[0].rank == 1
