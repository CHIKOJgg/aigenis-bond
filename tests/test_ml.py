"""Тесты ML: features + training + predict."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from ml.engine import (
    predict_one,
    train_buy_classifier,
    train_ytm_regressor,
)
from ml.features import build_dataset, build_features, features_to_matrix


def _bond(iid: str, ytm: float, cur: str, maturity: date, status: str = "active") -> dict:
    return {
        "internal_id": iid,
        "name": iid,
        "currency": cur,
        "yield_to_maturity": ytm,
        "coupon_rate": max(ytm - 1.0, 0.0),
        "maturity_date": maturity,
        "price": 100.0 - ytm,
        "status": status,
        "issuer": "Министерство финансов",
    }


def test_build_features_basic() -> None:
    today = date(2026, 6, 18)
    bond = _bond("OP-1", 5.0, "USD", date(2028, 6, 15))
    history = [
        {"date": today - timedelta(days=20), "price": 98.0, "yield": 5.5},
        {"date": today - timedelta(days=10), "price": 98.5, "yield": 5.3},
        {"date": today, "price": 99.0, "yield": 5.0},
    ]
    f = build_features(bond_dict=bond, history=history, asof=today)
    assert f.currency_idx == 0
    assert f.is_gov_issuer == 1
    assert f.duration_years > 1.5
    assert f.score > 0


def test_build_dataset() -> None:
    today = date(2026, 6, 18)
    bonds = [
        _bond("A", 5, "USD", date(2028, 1, 1)),
        _bond("B", 7, "BYN", date(2030, 1, 1)),
        _bond("C", 3, "XAU", date(2026, 1, 1)),
    ]
    history = {b["internal_id"]: [] for b in bonds}
    features = build_dataset(bonds, history, asof=today)
    assert len(features) == 3
    assert {f.internal_id for f in features} == {"A", "B", "C"}


def test_features_to_matrix_shape() -> None:
    today = date(2026, 6, 18)
    bond = _bond("A", 5, "USD", date(2028, 1, 1))
    features = [build_features(bond_dict=bond, asof=today)]
    X, names = features_to_matrix(features)
    assert len(X) == 1
    assert len(names) == len(X[0])
    assert "yield_to_maturity" in names


def test_train_predict_roundtrip(tmp_path: Path) -> None:
    today = date(2026, 6, 18)
    bonds = [_bond(f"B{i:03d}", 3 + i * 0.3, "USD", date(2028 + i, 1, 1)) for i in range(60)]
    history = {b["internal_id"]: [] for b in bonds}
    features = build_dataset(bonds, history, asof=today)

    mv_reg, _ = train_ytm_regressor(features)
    mv_clf, _ = train_buy_classifier(features)

    assert mv_reg.metrics.get("train_size", 0) > 0
    assert mv_clf.metrics.get("train_size", 0) > 0

    pred = predict_one(
        features[0],
        regressor_path=mv_reg.artifact_path,
        classifier_path=mv_clf.artifact_path,
    )
    assert pred.decision in {"buy", "hold", "wait", "avoid"}
    assert 0.0 <= pred.confidence <= 1.0
    assert pred.explanation
