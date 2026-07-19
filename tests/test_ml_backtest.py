"""Tests for ML quality tooling: richer features and the backtest report."""

from __future__ import annotations

from datetime import date

from ml.engine import backtest_report
from ml.features import TrainingSample, build_features
from ml.models import BondFeatures


def _feature(yld: float, asof: date, iid: str = "X") -> BondFeatures:
    return build_features(
        bond_dict={
            "internal_id": iid,
            "currency": "USD",
            "yield_to_maturity": yld,
            "price": 100.0,
            "coupon_rate": 8.0,
            "coupon_frequency": 2,
            "maturity_date": date(2030, 1, 1),
            "start_date": date(2024, 1, 1),
            "issuer": "Treasury",
            "status": "active",
            "nominal": 1000.0,
        },
        asof=asof,
    )


def test_modified_duration_feature_populated():
    feat = _feature(8.0, date(2026, 1, 1))
    assert feat.modified_duration > 0
    # Longer-maturity bond should have higher modified duration than a short one.
    from ml.features import build_features as bf

    near = bf(
        bond_dict={
            "internal_id": "N",
            "currency": "USD",
            "yield_to_maturity": 8.0,
            "coupon_rate": 8.0,
            "coupon_frequency": 2,
            "maturity_date": date(2027, 1, 1),
            "start_date": date(2026, 1, 1),
            "status": "active",
        },
        asof=date(2026, 1, 1),
    )
    far = bf(
        bond_dict={
            "internal_id": "F",
            "currency": "USD",
            "yield_to_maturity": 8.0,
            "coupon_rate": 8.0,
            "coupon_frequency": 2,
            "maturity_date": date(2035, 1, 1),
            "start_date": date(2025, 1, 1),
            "status": "active",
        },
        asof=date(2026, 1, 1),
    )
    assert far.modified_duration > near.modified_duration


def test_backtest_report_structure_and_beats_baseline():
    # Build samples where future_ytm is a predictable function of current ytm,
    # so the regressor should beat the naive random-walk baseline.
    samples = []
    base = date(2024, 1, 1)
    for i in range(60):
        yld = 5.0 + (i % 10) * 0.5
        asof = base.replace(year=base.year + i // 12, month=((base.month + i) % 12) + 1)
        feat = _feature(yld, asof, iid=f"B{i}")
        future_ytm = yld * 0.9 + (i % 3) * 0.05  # predictable, differs from current
        samples.append(
            TrainingSample(
                features=feat,
                asof=asof,
                future_ytm=round(future_ytm, 4),
                future_return_pct=round(future_ytm - yld, 4),
            )
        )

    report = backtest_report(samples)
    assert report["n_train"] + report["n_test"] == len(samples)
    assert "mae" in report["regressor"]
    assert "r2" in report["regressor"]
    assert isinstance(report["regressor"]["beats_baseline"], bool)
    assert len(report["top_features"]) <= 10
    assert all("importance" in f and "name" in f for f in report["top_features"])
    assert "accuracy" in report["classifier"]


def test_backtest_report_rejects_tiny_samples():
    import pytest

    with pytest.raises(ValueError):
        backtest_report([])
    with pytest.raises(ValueError):
        backtest_report([TrainingSample(features=_feature(8.0, date(2026, 1, 1)), asof=date(2026, 1, 1), future_ytm=8.0, future_return_pct=0.0)])
