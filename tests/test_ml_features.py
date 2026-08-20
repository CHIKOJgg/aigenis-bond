"""Comprehensive tests for ml.features (feature engineering + leakage-free samples)."""

from __future__ import annotations

from datetime import date, timedelta

from ml.features import (
    TrainingSample,
    _duration_years,
    _history_window,
    _momentum,
    _rolling_stats,
    _safe_float,
    build_dataset,
    build_features,
    build_training_samples,
    features_to_matrix,
)
from ml.models import BondFeatures


def test_safe_float_coercions():
    assert _safe_float(None) == 0.0
    assert _safe_float("3.5") == 3.5
    assert _safe_float(Decimal("2")) == 2.0
    assert _safe_float(object()) == 0.0
    assert _safe_float(5) == 5.0


def test_history_window_filters_by_date():
    asof = date(2024, 2, 15)
    hist = [
        {"date": date(2024, 1, 1), "yield": 10},
        {"date": date(2024, 2, 1), "yield": 11},
        {"date": date(2024, 3, 1), "yield": 12},
    ]
    win = _history_window(hist, asof, 30)
    # only rows within [asof-30d, asof] = [2024-01-16, 2024-02-15]
    assert {h["date"] for h in win} == {date(2024, 2, 1)}


def test_rolling_stats_mean_std():
    hist = [{"date": date(2024, 1, d), "yield": float(d)} for d in range(1, 6)]
    mean, std = _rolling_stats(hist, date(2024, 1, 3), 30)
    # only yields 1,2,3 fall within the window ending 2024-01-03
    assert mean == 2.0
    assert std > 0


def test_rolling_stats_empty():
    assert _rolling_stats([], date(2024, 1, 1), 30) == (0.0, 0.0)


def test_momentum_positive():
    hist = [
        {"date": date(2024, 1, 1), "yield": 10.0},
        {"date": date(2024, 1, 31), "yield": 12.0},
    ]
    assert _momentum(hist, date(2024, 1, 31), 30, "yield") == pytest.approx(0.2, abs=1e-6)


def test_momentum_too_few_points():
    hist = [{"date": date(2024, 1, 1), "yield": 10.0}]
    assert _momentum(hist, date(2024, 1, 1), 30, "yield") == 0.0


def test_duration_years_clamps_to_zero():
    assert _duration_years(None, date(2024, 1, 1)) == 0.0
    assert _duration_years(date(2020, 1, 1), date(2024, 1, 1)) == 0.0
    assert _duration_years(date(2026, 1, 1), date(2024, 1, 1)) > 0


def _bd(
    iid="B",
    ytm=10.0,
    currency="BYN",
    price=100.0,
    coupon=10.0,
    maturity=date(2028, 1, 1),
    issuer="ООО Рога",
    status="active",
    nominal=1000,
    coupon_frequency=2,
):
    return {
        "internal_id": iid,
        "currency": currency,
        "yield_to_maturity": ytm,
        "price": price,
        "coupon_rate": coupon,
        "maturity_date": maturity,
        "issuer": issuer,
        "status": status,
        "nominal": nominal,
        "coupon_frequency": coupon_frequency,
    }


def test_build_features_basic_fields():
    f = build_features(bond_dict=_bd(), asof=date(2024, 1, 1), avg_yield_by_currency={"BYN": 8.0})
    assert isinstance(f, BondFeatures)
    assert f.internal_id == "B"
    assert f.currency_idx == 2  # BYN
    assert f.spread_to_avg == pytest.approx(2.0, abs=1e-3)  # 10 - 8
    assert f.score is not None
    assert f.yield_to_maturity == 10.0


def test_build_features_gov_issuer_flag():
    f = build_features(bond_dict=_bd(issuer="Министерство финансов"), asof=date(2024, 1, 1))
    assert f.is_gov_issuer == 1


def test_build_features_usd_currency_idx():
    f = build_features(bond_dict=_bd(currency="USD"), asof=date(2024, 1, 1))
    assert f.currency_idx == 0


def test_features_to_matrix_shape_and_names():
    feats = [build_features(bond_dict=_bd(iid=f"B{i}"), asof=date(2024, 1, 1)) for i in range(3)]
    matrix, names = features_to_matrix(feats)
    assert len(matrix) == 3
    assert len(matrix[0]) == len(names) == 19


def test_build_dataset_uses_cross_sectional_avg():
    bonds = [_bd(iid="A", ytm=10), _bd(iid="B", ytm=12)]
    ds = build_dataset(bonds, {}, asof=date(2024, 1, 1))
    assert len(ds) == 2
    # average BYN yield is 11; A's spread should be -1, B's +1
    by_id = {f.internal_id: f for f in ds}
    assert by_id["A"].spread_to_avg == pytest.approx(-1.0, abs=1e-3)
    assert by_id["B"].spread_to_avg == pytest.approx(1.0, abs=1e-3)


def _hist_rows(start=date(2024, 1, 1), n=8, step=20, base_ytm=10.0):
    rows = []
    for i in range(n):
        d = start + timedelta(days=i * step)
        rows.append({"date": d, "yield": base_ytm + i * 0.5, "price": 100.0 + i})
    return rows


def test_build_training_samples_leakage_free():
    bonds = [_bd(iid="A", ytm=10.0)]
    history = {"A": _hist_rows()}
    samples = build_training_samples(
        bonds, history, horizon_days=90, tolerance_days=20, step_days=20, min_history_span_days=60
    )
    assert len(samples) > 0
    for s in samples:
        assert isinstance(s, TrainingSample)
        # The label (future_ytm) must differ from the feature's observed current ytm,
        # proving the target comes from the future, not the snapshot.
        assert s.future_ytm != s.features.yield_to_maturity
        assert s.future_return_pct == pytest.approx(
            s.future_ytm - s.features.yield_to_maturity, abs=1e-3
        )


def test_build_training_samples_requires_enough_history():
    bonds = [_bd(iid="A")]
    history = {"A": [{"date": date(2024, 1, 1), "yield": 10.0}]}
    assert build_training_samples(bonds, history) == []


from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
