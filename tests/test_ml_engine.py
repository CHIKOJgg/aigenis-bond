"""Comprehensive tests for ml.engine (decisions, splits, training, backtest)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from ml.engine import (
    _decide,
    _explanation,
    _outcome_label,
    _rolling_windows,
    _time_split,
    _version_from_path,
    backtest_report,
    train_buy_classifier,
    train_ytm_regressor,
)
from ml.features import TrainingSample
from ml.models import BondFeatures


def _feat(iid="B", ytm=10.0, score=70.0, asof=date(2024, 1, 1),
          duration_years=3.0, spread=1.5, metal=0.0, is_gov=False):
    return BondFeatures(
        internal_id=iid,
        asof_date=asof,
        currency_idx=2,
        duration_years=duration_years,
        days_to_maturity=duration_years * 365.25,
        modified_duration=duration_years,
        coupon_rate=10.0,
        price=100.0,
        yield_to_maturity=ytm,
        spread_to_avg=spread,
        rolling_yield_mean_30d=ytm,
        rolling_yield_std_30d=0.0,
        yield_momentum_30d=0.0,
        price_momentum_30d=0.0,
        score=score,
        score_yield_component=10.0,
        score_currency_component=14.0,
        score_duration_component=5.0,
        score_metal_component=metal,
        is_gov_issuer=1 if is_gov else 0,
        is_active=1,
    )


# --- pure decision logic ---------------------------------------------------

def test_outcome_label_mapping():
    assert _outcome_label(-0.5) == 2   # falling yield -> buy
    assert _outcome_label(0.6) == 0    # rising yield -> avoid
    assert _outcome_label(0.1) == 1    # hold


def test_decide_low_score_avoids():
    assert _decide(30, None) == "avoid"
    assert _decide(39, -0.3) == "avoid"


def test_decide_buy_when_yield_falls():
    assert _decide(70, -0.3) == "buy"
    assert _decide(70, -1.0) == "buy"


def test_decide_wait_when_yield_rises():
    assert _decide(70, 0.7) == "wait"


def test_decide_high_score_buys_without_forecast():
    assert _decide(80, None) == "buy"


def test_decide_hold_default():
    assert _decide(60, None) == "hold"


def test_explanation_includes_notes():
    f = _feat(score=80, spread=2.0, duration_years=1.5, is_gov=True)
    notes = _explanation(f, predicted_ytm=9.5)
    assert any("выше средней" in n for n in notes)
    assert any("высокий" in n for n in notes)
    assert any("короткая" in n for n in notes)
    assert any("государство" in n for n in notes)


def test_version_from_path():
    assert _version_from_path("artifacts/ytm_regressor_20240101120000.joblib") == "20240101120000"
    assert _version_from_path("x/buy_classifier_abc.joblib") == "abc"
    assert _version_from_path(None) is None


# --- walk-forward splits (no future leakage) -------------------------------

def test_time_split_keeps_order_and_holds_out_recent():
    samples = [
        TrainingSample(features=_feat(asof=date(2024, 1, 1 + i)), asof=date(2024, 1, 1 + i),
                       future_ytm=10.0, future_return_pct=0.0)
        for i in range(20)
    ]
    train, test = _time_split(samples)
    assert len(train) == 15 and len(test) == 5
    # earlier samples in train, later in test
    assert max(s.asof for s in train) < min(s.asof for s in test)


def test_rolling_windows_expanding():
    samples = [
        TrainingSample(features=_feat(asof=date(2024, 1, 1) + timedelta(days=i)),
                       asof=date(2024, 1, 1) + timedelta(days=i),
                       future_ytm=10.0, future_return_pct=0.0)
        for i in range(40)
    ]
    folds = _rolling_windows(samples, n_folds=5)
    assert len(folds) >= 1
    for tr, te in folds:
        # each fold's train is an earlier prefix than its test
        assert max(s.asof for s in tr) < min(s.asof for s in te)


# --- end-to-end training / backtest with synthetic data --------------------

def _make_samples(n=40):
    out = []
    for i in range(n):
        asof = date(2024, 1, 1) + timedelta(days=5 * i)
        ytm = 8.0 + (i % 7)
        # alternate the realized move so both classifier classes appear
        future_return = -0.5 if i % 2 == 0 else 0.6
        out.append(TrainingSample(
            features=_feat(iid=f"B{i}", ytm=ytm, asof=asof),
            asof=asof,
            future_ytm=ytm + future_return,
            future_return_pct=future_return,
        ))
    return out


def test_backtest_report_returns_metrics():
    report = backtest_report(_make_samples(40), target_horizon_days=90)
    assert report["n_train"] + report["n_test"] == 40
    assert "mae" in report["regressor"]
    assert "accuracy" in report["classifier"]
    assert "top_features" in report
    assert len(report["top_features"]) <= 10


def test_train_ytm_regressor_produces_model_version():
    mv, run = train_ytm_regressor(_make_samples(40))
    assert mv.kind == "ytm_regression"
    assert "mae" in mv.metrics
    assert mv.metrics["train_size"] + mv.metrics["test_size"] == 40
    assert run.status == "ok"


def test_train_buy_classifier_produces_model_version():
    mv, run = train_buy_classifier(_make_samples(40))
    assert mv.kind == "buy_classifier"
    assert "accuracy" in mv.metrics
    assert run.status == "ok"


def test_train_requires_minimum_samples():
    with pytest.raises(ValueError):
        train_ytm_regressor([])
    with pytest.raises(ValueError):
        train_buy_classifier(_make_samples(10))
