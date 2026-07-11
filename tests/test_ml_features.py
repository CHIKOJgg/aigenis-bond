"""Unit tests for ML feature engineering (ml/features.py)."""
from __future__ import annotations

from datetime import date, datetime

from ml.features import build_dataset, build_features, features_to_matrix
from ml.models import BondFeatures


def _bond_dict(
    *,
    internal_id: str = "OP-1",
    ytm: float = 9.0,
    currency: str = "USD",
    coupon: float = 8.0,
    price: float = 100.0,
    maturity: str = "2030-01-01",
    status: str = "active",
    issuer: str = "Treasury",
) -> dict:
    return {
        "internal_id": internal_id,
        "yield_to_maturity": ytm,
        "currency": currency,
        "coupon_rate": coupon,
        "price": price,
        "maturity_date": datetime.strptime(maturity, "%Y-%m-%d").date(),
        "status": status,
        "issuer": issuer,
    }


def test_build_features_basic_fields():
    f = build_features(bond_dict=_bond_dict(), asof=date(2026, 1, 1))
    assert isinstance(f, BondFeatures)
    assert f.internal_id == "OP-1"
    assert f.currency_idx == 0  # USD
    assert f.yield_to_maturity == 9.0
    assert f.is_gov_issuer == 1  # "Treasury"
    assert f.is_active == 1
    assert f.duration_years > 0


def test_build_features_spread_to_avg():
    bonds = [_bond_dict(internal_id="A", ytm=10.0), _bond_dict(internal_id="B", ytm=8.0)]
    f = build_features(bond_dict=bonds[0], avg_yield_by_currency={"USD": 9.0}, asof=date(2026, 1, 1))
    assert f.spread_to_avg == 1.0  # 10 - 9


def test_build_features_history_momentum():
    history = [
        {"date": date(2026, 1, 1), "yield": 9.0, "price": 100.0},
        {"date": date(2026, 1, 15), "yield": 10.0, "price": 99.0},
    ]
    f = build_features(
        bond_dict=_bond_dict(ytm=10.0),
        history=history,
        asof=date(2026, 1, 15),
    )
    assert f.rolling_yield_mean_30d > 0
    assert f.yield_momentum_30d > 0  # yield rose 9→10
    assert f.is_gov_issuer == 1


def test_build_features_unknown_currency_idx():
    f = build_features(bond_dict=_bond_dict(currency="RUB"), asof=date(2026, 1, 1))
    assert f.currency_idx == 99


def test_build_dataset_avg_by_currency():
    bonds = [_bond_dict(internal_id="A", ytm=10.0), _bond_dict(internal_id="B", ytm=8.0)]
    ds = build_dataset(bonds, {}, asof=date(2026, 1, 1))
    assert len(ds) == 2
    # Both USD: A's spread should be +1, B's -1 (avg of 10 and 8 is 9).
    by_id = {f.internal_id: f for f in ds}
    assert by_id["A"].spread_to_avg == 1.0
    assert by_id["B"].spread_to_avg == -1.0


def test_features_to_matrix_shape_and_names():
    f = build_features(bond_dict=_bond_dict(), asof=date(2026, 1, 1))
    matrix, names = features_to_matrix([f])
    assert len(matrix) == 1
    assert len(matrix[0]) == len(names) == 18
    assert "yield_to_maturity" in names
    assert "is_gov_issuer" in names
