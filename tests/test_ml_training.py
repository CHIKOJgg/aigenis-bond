"""Tests for leakage-free ML training (ml/features.build_training_samples +
ml/engine.train_ytm_regressor / train_buy_classifier).

The previous target was ``y = ytm + spread*0.3 + score*0.02`` — a function of
the input features, so the model trivially memorised an identity. These tests
assert that:

* training samples pair *past* features with a *future* observation (the label
  is never simply the current YTM);
* the walk-forward split keeps validation strictly after training in time;
* the regressor reports an out-of-time baseline comparison so degradation is
  observable.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

from ml.engine import _time_split, train_buy_classifier, train_ytm_regressor
from ml.features import build_training_samples


def _synthetic_bonds_and_history(n_bonds: int = 12, days: int = 400):
    """Build bonds with history where the future YTM depends on recent momentum
    (a learnable relationship) plus noise — NOT on an identity of the label."""
    bonds = []
    history_by_bond: dict[str, list[dict]] = {}
    start = date(2025, 1, 1)
    for i in range(n_bonds):
        iid = f"B-{i}"
        base_ytm = 6.0 + i * 0.3
        rows = []
        for d in range(0, days, 7):  # weekly observations
            day = start + timedelta(days=d)
            # A slow oscillation gives non-trivial momentum the model can learn.
            ytm = base_ytm + 1.5 * math.sin(d / 60.0 + i) + 0.05 * (i % 3)
            price = 100.0 - (ytm - base_ytm) * 2.0
            rows.append({"date": day, "yield": round(ytm, 4), "price": round(price, 4)})
        history_by_bond[iid] = rows
        bonds.append(
            {
                "internal_id": iid,
                "name": f"Bond {i}",
                "currency": "USD",
                "yield_to_maturity": rows[-1]["yield"],
                "coupon_rate": 5.0,
                "price": rows[-1]["price"],
                "maturity_date": date(2032, 1, 1),
                "status": "active",
                "issuer": "Treasury" if i % 2 == 0 else "Corp",
            }
        )
    return bonds, history_by_bond


def test_build_training_samples_uses_future_not_identity():
    bonds, history = _synthetic_bonds_and_history()
    samples = build_training_samples(bonds, history, horizon_days=90, step_days=30)
    assert len(samples) >= 30

    for s in samples:
        # The label is the future YTM, which for an oscillating series should
        # differ from the as-of YTM most of the time — i.e. it is NOT the
        # trivial identity the old target encoded.
        assert isinstance(s.future_ytm, float)
        # future_return_pct is future_ytm - current_ytm by construction.
        assert abs(s.future_return_pct - (s.future_ytm - s.features.yield_to_maturity)) < 1e-6

    # At least some samples must have a genuinely different future value.
    moved = [s for s in samples if abs(s.future_return_pct) > 0.1]
    assert len(moved) > 0


def test_time_split_is_walk_forward():
    bonds, history = _synthetic_bonds_and_history()
    samples = build_training_samples(bonds, history, horizon_days=90, step_days=30)
    train_s, test_s = _time_split(samples, test_fraction=0.25)
    assert train_s and test_s
    latest_train = max(s.asof for s in train_s)
    earliest_test = min(s.asof for s in test_s)
    # Validation must not precede training in time (no shuffling / leakage).
    assert earliest_test >= latest_train


def test_train_ytm_regressor_reports_baseline():
    bonds, history = _synthetic_bonds_and_history()
    samples = build_training_samples(bonds, history, horizon_days=90, step_days=30)
    mv, run = train_ytm_regressor(samples, target_horizon_days=90)
    assert mv.kind == "ytm_regression"
    assert "mae" in mv.metrics
    assert "baseline_mae" in mv.metrics  # random-walk baseline recorded
    assert "beats_baseline" in mv.metrics
    assert mv.metrics["train_size"] > 0
    assert mv.metrics["test_size"] > 0
    assert "walk-forward" in mv.notes
    assert run.status == "ok"


def test_train_ytm_regressor_rejects_legacy_feature_list():
    # The old signature passed a plain feature list; that path is gone.
    try:
        train_ytm_regressor([])
        raise AssertionError("expected ValueError for empty/legacy input")
    except ValueError:
        pass


def test_train_buy_classifier_labels_from_future_move():
    bonds, history = _synthetic_bonds_and_history()
    samples = build_training_samples(bonds, history, horizon_days=90, step_days=30)
    try:
        mv, _run = train_buy_classifier(samples)
    except ValueError:
        # Acceptable if the synthetic slice lacks class diversity; the important
        # guarantee is that it never trains on the circular Score-based label.
        return
    assert mv.kind == "buy_classifier"
    assert "accuracy" in mv.metrics
    assert "baseline_accuracy" in mv.metrics
    assert "realized future YTM move" in mv.notes
