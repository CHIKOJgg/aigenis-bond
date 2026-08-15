"""Audit test suite: ml/engine.py, ml/repository.py, monitoring/metrics.py,
monitoring/engine.py, forecast/engine.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import forecast.engine as fc
import ml.engine as engine
import ml.registry as registry
import monitoring.engine as mon_engine
import monitoring.metrics as metrics_mod
from ml.engine import (
    _cv_mae,
    _decide,
    _outcome_label,
    _rolling_windows,
    _time_split,
    _version_from_path,
    backtest_report,
    predict_batch,
    predict_one,
    train_buy_classifier,
    train_ytm_regressor,
)
from ml.features import TrainingSample
from ml.models import BondFeatures
from ml.repository import (
    insert_training_run,
    latest_model_version,
    latest_predictions,
    predictions_for_bond,
    upsert_model_version,
    upsert_predictions,
)
from scraper.db import session_scope
from scraper.orm import AlertORM, BondHistoryORM, BondORM, BondScoreORM, FxRateORM, MetalPriceORM

VERSION = "20260101000000audit"
TRAIN_MIN = 30


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _make_feature(iid: str, asof: date, ytm: float, score: float = 60.0) -> BondFeatures:
    """A BondFeatures with full required fields; no scoring-engine dependency."""
    duration = 3.0 + (iid.__hash__() % 5 if False else 2.0)
    return BondFeatures(
        internal_id=iid,
        asof_date=asof,
        currency_idx=0,
        duration_years=round(duration, 4),
        days_to_maturity=round(duration * 365.25, 2),
        coupon_rate=8.0,
        price=100.0,
        yield_to_maturity=ytm,
        spread_to_avg=0.5,
        rolling_yield_mean_30d=ytm,
        rolling_yield_std_30d=0.1,
        yield_momentum_30d=0.01,
        price_momentum_30d=0.01,
        score=score,
        score_yield_component=30.0,
        score_currency_component=10.0,
        score_duration_component=10.0,
        score_metal_component=0.0,
        is_gov_issuer=0,
        is_active=1,
    )


def _make_samples(n: int, base: date = date(2024, 1, 1)) -> list[TrainingSample]:
    """Deterministic training samples: ytm varies, realized YTM move cycles
    through the three outcome classes so the classifier slice is diverse."""
    samples: list[TrainingSample] = []
    for i in range(n):
        asof = base + timedelta(days=i * 7)
        ytm = 6.0 + (i % 12) * 0.5
        move = [-0.6, 0.0, 0.8][i % 3]
        feat = _make_feature(f"B{i}", asof, ytm, score=50.0 + (i % 5) * 10.0)
        samples.append(
            TrainingSample(
                features=feat,
                asof=asof,
                future_ytm=round(ytm + move, 4),
                future_return_pct=move,
            )
        )
    return samples


def _all_buy_samples(n: int) -> list[TrainingSample]:
    """30+ samples whose realized move is always <= -0.25 -> a single class."""
    out: list[TrainingSample] = []
    for i in range(n):
        asof = date(2024, 1, 1) + timedelta(days=i * 7)
        ytm = 8.0
        feat = _make_feature(f"B{i}", asof, ytm, score=80.0)
        out.append(
            TrainingSample(
                features=feat,
                asof=asof,
                future_ytm=round(ytm - 1.0, 4),
                future_return_pct=-1.0,
            )
        )
    return out


@pytest.fixture(scope="module", autouse=True)
def _isolated_artifacts(tmp_path_factory):
    """Redirect ALL artifact IO to a tmp dir for this module (never touches
    the real ml/artifacts directory)."""
    d = tmp_path_factory.mktemp("audit_artifacts")
    old_reg, old_eng = registry.ARTIFACTS_DIR, engine.ARTIFACTS_DIR
    registry.ARTIFACTS_DIR = d
    engine.ARTIFACTS_DIR = d
    yield d
    registry.ARTIFACTS_DIR = old_reg
    engine.ARTIFACTS_DIR = old_eng


@pytest.fixture(scope="module")
def samples_30() -> list[TrainingSample]:
    return _make_samples(TRAIN_MIN)


@pytest.fixture(scope="module")
def reg_trained(samples_30, _isolated_artifacts):
    return train_ytm_regressor(samples_30, version=VERSION)


@pytest.fixture(scope="module")
def clf_trained(samples_30, _isolated_artifacts):
    return train_buy_classifier(samples_30, version=VERSION)


@pytest.fixture(scope="module")
def reg_artifact(reg_trained) -> str:
    return reg_trained[0].artifact_path


@pytest.fixture(scope="module")
def clf_artifact(clf_trained) -> str:
    return clf_trained[0].artifact_path


# --------------------------------------------------------------------------- #
# ml/engine.py: small pure helpers
# --------------------------------------------------------------------------- #


def test_version_from_path_basics():
    assert _version_from_path(None) is None
    assert _version_from_path("") is None
    assert _version_from_path("ytm_regressor_20240101120000") == "20240101120000"
    assert _version_from_path("buy_classifier_abc") == "abc"
    assert _version_from_path("volatility_1") == "1"


def test_version_from_path_rejects_unrecognised_names():
    assert _version_from_path("other_name") is None
    assert _version_from_path("ytm_regressor") is None  # prefix needs the underscore


def test_version_from_path_full_path_with_suffix():
    p = str(Path("ml/artifacts") / f"ytm_regressor_{VERSION}.joblib")
    assert _version_from_path(p) == VERSION


# _decide semantics (matching the classifier labels in _outcome_label:
# predicted_return = predicted YTM - current YTM; <= -0.25 -> yield falling,
# price rising -> buy; >= 0.5 -> yield rising sharply -> wait; neutral band
# falls back to the score; score < 40 is always avoid).
_DECIDE_CASES = [
    (90, -1.0, "buy"),
    (90, 1.0, "wait"),
    (90, 3.0, "wait"),
    (90, -0.2, "buy"),
    (90, -0.25, "buy"),
    (90, 0.5, "wait"),
    (90, None, "buy"),
    (50, -5.0, "buy"),
    (39, -5.0, "avoid"),
    (39, 5.0, "avoid"),
    (75, None, "buy"),
]


@pytest.mark.parametrize("score,predicted_return,expected", _DECIDE_CASES)
def test__decide_matrix(score, predicted_return, expected):
    assert _decide(score, predicted_return) == expected


def test__decide_score_below_40_always_avoid_even_with_strong_buy_signal():
    assert _decide(39, -5.0) == "avoid"
    assert _decide(0, None) == "avoid"


def test__decide_boundary_75_with_neutral_prediction_is_buy():
    assert _decide(75, -0.2) == "buy"
    assert _decide(75, 0.4) == "buy"


def test_time_split_empty_returns_two_empty_lists():
    # len 0 -> cut clamped to 1 -> ordered[:1] == [] and ordered[1:] == [].
    train_s, test_s = _time_split([])
    assert train_s == []
    assert test_s == []


def test_time_split_single_sample_keeps_train_only():
    samples = _make_samples(1)
    train_s, test_s = _time_split(samples)
    assert len(train_s) == 1
    assert len(test_s) == 0


def test_time_split_preserves_order_and_fraction():
    samples = _make_samples(10)
    shuffled = [
        samples[3],
        samples[0],
        samples[9],
        samples[4],
        samples[1],
        samples[5],
        samples[2],
        samples[6],
        samples[8],
        samples[7],
    ]
    train_s, test_s = _time_split(shuffled, test_fraction=0.5)
    assert len(train_s) == 5 and len(test_s) == 5
    all_asof = [s.asof for s in train_s + test_s]
    assert all_asof == sorted(all_asof)
    assert max(s.asof for s in train_s) <= min(s.asof for s in test_s)


def test_rolling_windows_small_sample_single_fold():
    folds = _rolling_windows(_make_samples(9), n_folds=5)
    assert len(folds) == 1
    train_s, test_s = folds[0]
    assert len(train_s) == 6 and len(test_s) == 3  # _time_split at 0.25


def test_rolling_windows_n20_four_folds():
    folds = _rolling_windows(_make_samples(20), n_folds=5)
    assert len(folds) == 4
    sizes = [(len(t), len(te)) for t, te in folds]
    assert sizes == [(4, 16), (8, 12), (12, 8), (16, 4)]  # cuts 4,8,12,16
    for train_s, test_s in folds:
        assert max(s.asof for s in train_s) < min(s.asof for s in test_s)


def test_rolling_windows_folds_never_overlap_in_time():
    folds = _rolling_windows(_make_samples(40), n_folds=5)
    assert len(folds) == 4
    for train_s, test_s in folds:
        train_dates = [s.asof for s in train_s]
        test_dates = [s.asof for s in test_s]
        assert train_dates == sorted(train_dates)
        assert max(train_dates) < min(test_dates)


def test_cv_mae_zero_when_train_slices_too_small():
    # n=18 -> step 3 -> trains 3/6/9/12, all < 15 -> every fold skipped.
    assert _cv_mae(_make_samples(18)) == 0.0


def test_cv_mae_non_negative_with_qualifying_folds():
    cv = _cv_mae(_make_samples(30))
    assert isinstance(cv, float)
    assert cv >= 0.0


def test_outcome_label_default_thresholds():
    assert _outcome_label(-1.0) == 2
    assert _outcome_label(-0.25) == 2  # boundary inclusive
    assert _outcome_label(-0.24) == 1
    assert _outcome_label(0.0) == 1
    assert _outcome_label(0.49) == 1
    assert _outcome_label(0.5) == 0  # boundary inclusive
    assert _outcome_label(5.0) == 0


def test_outcome_label_custom_thresholds():
    assert _outcome_label(-0.5, buy_threshold_pct=-0.5, avoid_threshold_pct=1.0) == 2
    assert _outcome_label(-0.49, buy_threshold_pct=-0.5, avoid_threshold_pct=1.0) == 1
    assert _outcome_label(1.0, buy_threshold_pct=-0.5, avoid_threshold_pct=1.0) == 0
    assert _outcome_label(0.99, buy_threshold_pct=-0.5, avoid_threshold_pct=1.0) == 1


# --------------------------------------------------------------------------- #
# ml/engine.py: training
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad", [None, [], [1, 2]])
def test_train_ytm_regressor_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        train_ytm_regressor(bad)


def test_train_ytm_regressor_rejects_fewer_than_30():
    with pytest.raises(ValueError):
        train_ytm_regressor(_make_samples(29))


def test_train_ytm_regressor_success(reg_trained):
    mv, run = reg_trained
    assert mv.kind == "ytm_regression"
    assert run.kind == "ytm_regression"
    for key in ("mae", "r2", "baseline_mae", "beats_baseline", "cv_mae", "train_size", "test_size"):
        assert key in mv.metrics
    assert mv.metrics["beats_baseline"] in (0.0, 1.0)
    assert mv.metrics["train_size"] > 0 and mv.metrics["test_size"] > 0
    assert mv.metrics["train_size"] + mv.metrics["test_size"] == TRAIN_MIN
    assert mv.train_rows == TRAIN_MIN
    assert run.status == "ok"
    assert mv.trained_at.tzinfo is not None  # UTC
    assert "horizon_days=90" in mv.notes


def test_train_ytm_regressor_writes_joblib_with_version(reg_trained):
    mv, _run = reg_trained
    assert mv.artifact_path.endswith(".joblib")
    assert f"ytm_regressor_{VERSION}.joblib" in mv.artifact_path
    assert Path(mv.artifact_path).exists()


@pytest.mark.parametrize("bad", [None, [], [1, 2]])
def test_train_buy_classifier_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        train_buy_classifier(bad)


def test_train_buy_classifier_rejects_fewer_than_30():
    with pytest.raises(ValueError):
        train_buy_classifier(_make_samples(29))


def test_train_buy_classifier_single_class_train_slice_raises():
    with pytest.raises(ValueError, match="single outcome class"):
        train_buy_classifier(_all_buy_samples(30))


def test_train_buy_classifier_success(clf_trained):
    mv, run = clf_trained
    assert mv.kind == "buy_classifier"
    for key in ("accuracy", "baseline_accuracy", "beats_baseline", "train_size", "test_size"):
        assert key in mv.metrics
    assert 0.0 <= mv.metrics["accuracy"] <= 1.0
    assert 0.0 <= mv.metrics["baseline_accuracy"] <= 1.0
    assert run.status == "ok"
    assert Path(mv.artifact_path).exists()
    assert f"buy_classifier_{VERSION}.joblib" in mv.artifact_path
    assert "realized future YTM move" in mv.notes


def test_backtest_report_rejects_empty_and_small():
    with pytest.raises(ValueError):
        backtest_report([])
    with pytest.raises(ValueError):
        backtest_report(_make_samples(29))


def test_backtest_report_structure(samples_30):
    report = backtest_report(samples_30, target_horizon_days=90)
    assert set(report) == {
        "horizon_days",
        "n_train",
        "n_test",
        "regressor",
        "classifier",
        "top_features",
    }
    assert report["horizon_days"] == 90
    assert report["n_train"] + report["n_test"] == TRAIN_MIN
    assert report["n_train"] == 22 and report["n_test"] == 8
    for key in ("mae", "r2", "baseline_mae", "cv_mae"):
        assert key in report["regressor"]
    assert isinstance(report["regressor"]["beats_baseline"], bool)
    for key in ("accuracy", "baseline_accuracy", "beats_baseline"):
        assert key in report["classifier"]
    assert isinstance(report["classifier"]["beats_baseline"], bool)
    assert report["top_features"]
    for f in report["top_features"]:
        assert {"name", "importance"} == set(f)
    assert len(report["top_features"]) <= 10


# --------------------------------------------------------------------------- #
# ml/engine.py: predict_one / predict_batch / latest_artifact
# --------------------------------------------------------------------------- #


def test_predict_one_no_models_uses_score():
    f = _make_feature("X1", date(2026, 1, 1), 9.0, score=90.0)
    p = predict_one(f, regressor_path=None, classifier_path=None)
    assert p.model_kind == "ytm_regression"
    assert p.model_version == "latest"
    assert p.predicted_ytm is None
    assert p.predicted_return_pct is None
    assert p.decision == "buy"
    assert p.confidence == 0.9
    assert p.internal_id == "X1"

    low = predict_one(
        _make_feature("X2", date(2026, 1, 1), 9.0, score=30.0),
        regressor_path=None,
        classifier_path=None,
    )
    assert low.decision == "avoid"
    assert low.confidence == 0.3

    mid = predict_one(
        _make_feature("X3", date(2026, 1, 1), 9.0, score=50.0),
        regressor_path=None,
        classifier_path=None,
    )
    assert mid.decision == "hold"

    hi = predict_one(
        _make_feature("X4", date(2026, 1, 1), 9.0, score=150.0),
        regressor_path=None,
        classifier_path=None,
    )
    assert hi.confidence == 1.0


def test_predict_one_regressor_only(reg_artifact):
    f = _make_feature("R1", date(2026, 1, 1), 9.5, score=70.0)
    p = predict_one(f, regressor_path=reg_artifact, classifier_path=None)
    assert p.model_kind == "ytm_regression"
    assert p.model_version == VERSION
    assert p.predicted_ytm is not None
    assert p.predicted_return_pct == pytest.approx(p.predicted_ytm - f.yield_to_maturity, abs=1e-9)
    assert p.decision == _decide(f.score, p.predicted_return_pct)
    assert p.feature_importance
    values = list(p.feature_importance.values())
    assert values == sorted(values, reverse=True)


def _matrix(f):
    from ml.features import features_to_matrix

    x_mat, _ = features_to_matrix([f])
    return x_mat


def test_predict_one_classifier_only(clf_artifact):
    from ml.engine import _DECISION_FROM_CLASS

    f = _make_feature("C1", date(2026, 1, 1), 9.0, score=60.0)
    p = predict_one(f, regressor_path=None, classifier_path=clf_artifact)
    bundle = engine.load_artifact(clf_artifact)
    proba = bundle["model"].predict_proba(bundle["scaler"].transform(_matrix(f)))[0]
    best_class = int(list(bundle["model"].classes_)[int(proba.argmax())])
    assert p.decision == _DECISION_FROM_CLASS[best_class]
    assert p.model_kind == "buy_classifier"
    assert p.model_version == VERSION
    assert p.confidence == round(float(proba.max()), 3)
    assert p.predicted_ytm is None


def test_predict_one_combined(reg_artifact, clf_artifact):
    from ml.engine import _DECISION_FROM_CLASS

    f = _make_feature("M1", date(2026, 1, 1), 9.0, score=80.0)
    p = predict_one(f, regressor_path=reg_artifact, classifier_path=clf_artifact)
    assert p.model_kind == "combined"
    assert p.model_version == f"{VERSION}+{VERSION}"
    assert p.predicted_ytm is not None
    bundle = engine.load_artifact(clf_artifact)
    proba = bundle["model"].predict_proba(bundle["scaler"].transform(_matrix(f)))[0]
    best_class = int(list(bundle["model"].classes_)[int(proba.argmax())])
    assert p.decision == _DECISION_FROM_CLASS[best_class]
    assert p.confidence == round(float(proba.max()), 3)


def test_predict_batch_preserves_ids_and_length():
    feats = [
        _make_feature("P1", date(2026, 1, 1), 8.0, score=90.0),
        _make_feature("P2", date(2026, 1, 1), 9.0, score=50.0),
        _make_feature("P3", date(2026, 1, 1), 10.0, score=20.0),
    ]
    preds = predict_batch(feats, regressor_path=None, classifier_path=None)
    assert len(preds) == 3
    assert [p.internal_id for p in preds] == ["P1", "P2", "P3"]
    assert predict_batch([], regressor_path=None, classifier_path=None) == []


def test_latest_artifact_none_when_nothing_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ARTIFACTS_DIR", tmp_path / "empty")
    for kind in ("ytm_regression", "buy_classifier", "volatility"):
        assert engine.latest_artifact(kind) is None


def test_latest_artifact_returns_path_str(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "ARTIFACTS_DIR", tmp_path / "artifacts")
    registry.save_artifact(tmp_path / "artifacts" / "ytm_regressor_v1.joblib", {"model": "m"})
    result = engine.latest_artifact("ytm_regression")
    assert isinstance(result, str)
    assert result.endswith(".joblib")


def test_load_artifact_alias(reg_artifact):
    bundle = engine.load_artifact(reg_artifact)
    assert set(bundle) == {"model", "scaler", "features"}


# --------------------------------------------------------------------------- #
# ml/repository.py (DB-backed)
# --------------------------------------------------------------------------- #


def _mv(version: str, trained_at: datetime, mae: float = 1.0) -> object:
    from ml.models import ModelVersion

    return ModelVersion(
        version=version,
        kind="ytm_regression",
        metrics={"mae": mae},
        trained_at=trained_at,
        train_rows=30,
        artifact_path=f"artifacts/{version}.joblib",
        notes="note",
    )


def _run(version: str) -> object:
    from ml.models import TrainingRun

    return TrainingRun(
        version=version,
        kind="ytm_regression",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        finished_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        metrics={"mae": 0.5},
        status="ok",
        notes="run",
    )


def _pred(
    iid: str,
    asof: date,
    version: str,
    *,
    decision: str = "buy",
    created_at: datetime | None = None,
) -> object:
    from ml.models import Prediction

    return Prediction(
        internal_id=iid,
        model_version=version,
        model_kind="ytm_regression",
        asof_date=asof,
        predicted_ytm=8.5,
        predicted_return_pct=-0.5,
        decision=decision,
        confidence=0.7,
        feature_importance={"score": 0.1},
        explanation=["note"],
        created_at=created_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_repo_latest_model_version_empty_is_none():
    async with session_scope() as s:
        assert await latest_model_version(s, "ytm_regression") is None


async def test_repo_upsert_and_latest_ordering():
    async with session_scope() as s:
        await upsert_model_version(s, _mv("v1", datetime(2026, 1, 1, tzinfo=UTC)))
        await upsert_model_version(s, _mv("v2", datetime(2026, 1, 2, tzinfo=UTC)))
        await upsert_model_version(s, _mv("v3", datetime(2026, 1, 3, tzinfo=UTC), mae=0.1))
    async with session_scope() as s:
        latest = await latest_model_version(s, "ytm_regression")
        assert latest is not None and latest.version == "v3"
        assert latest.metrics == {"mae": 0.1}
        assert latest.kind == "ytm_regression"


async def test_repo_upsert_same_version_updates_not_duplicates():
    async with session_scope() as s:
        await upsert_model_version(s, _mv("v1", datetime(2026, 1, 1, tzinfo=UTC), mae=1.0))
    async with session_scope() as s:
        await upsert_model_version(s, _mv("v1", datetime(2026, 1, 1, tzinfo=UTC), mae=9.9))
    from sqlalchemy import select

    from scraper.orm import ModelVersionORM

    async with session_scope() as s:
        rows = list((await s.execute(select(ModelVersionORM))).scalars().all())
        assert len(rows) == 1
        assert rows[0].metrics == {"mae": 9.9}


async def test_repo_latest_kind_filtered():
    from ml.models import ModelVersion

    async with session_scope() as s:
        await upsert_model_version(s, _mv("v1", datetime(2026, 1, 1, tzinfo=UTC)))
        await upsert_model_version(
            s,
            ModelVersion(
                version="c1",
                kind="buy_classifier",
                metrics={"accuracy": 0.8},
                trained_at=datetime(2026, 1, 5, tzinfo=UTC),
                train_rows=30,
                artifact_path="c1.joblib",
                notes="",
            ),
        )
    async with session_scope() as s:
        assert (await latest_model_version(s, "buy_classifier")).version == "c1"
        assert (await latest_model_version(s, "ytm_regression")).version == "v1"
        assert await latest_model_version(s, "volatility") is None


async def test_repo_insert_training_run():
    async with session_scope() as s:
        await insert_training_run(s, _run("v1"))
    from sqlalchemy import select

    from scraper.orm import TrainingRunORM

    async with session_scope() as s:
        rows = list((await s.execute(select(TrainingRunORM))).scalars().all())
        assert len(rows) == 1
        assert rows[0].version == "v1"
        assert rows[0].status == "ok"
        assert rows[0].metrics == {"mae": 0.5}
        assert rows[0].finished_at is not None


async def test_repo_upsert_predictions_inserts_and_counts():
    preds = [
        _pred("B1", date(2026, 1, 1), "v1"),
        _pred("B2", date(2026, 1, 1), "v1"),
    ]
    async with session_scope() as s:
        n = await upsert_predictions(s, preds)
        assert n == 2
    async with session_scope() as s:
        rows = await latest_predictions(s)
        assert len(rows) == 2


async def test_repo_upsert_predictions_empty_returns_zero():
    async with session_scope() as s:
        assert await upsert_predictions(s, []) == 0


async def test_repo_upsert_predictions_updates_existing_key():
    first = _pred("B1", date(2026, 1, 1), "v1", decision="buy")
    async with session_scope() as s:
        await upsert_predictions(s, [first])
    updated = _pred("B1", date(2026, 1, 1), "v1", decision="hold")
    async with session_scope() as s:
        await upsert_predictions(s, [updated])
    async with session_scope() as s:
        rows = await latest_predictions(s)
        assert len(rows) == 1
        assert rows[0].decision == "hold"
        assert rows[0].internal_id == "B1"


async def test_repo_latest_predictions_ordering_and_filter():
    old = _pred(
        "B1", date(2026, 1, 1), "v1", decision="hold", created_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    new = _pred(
        "B2", date(2026, 1, 2), "v1", decision="buy", created_at=datetime(2026, 1, 2, tzinfo=UTC)
    )
    async with session_scope() as s:
        await upsert_predictions(s, [old, new])
    async with session_scope() as s:
        rows = await latest_predictions(s)
        assert [r.internal_id for r in rows] == ["B2", "B1"]
        buy_only = await latest_predictions(s, decision="buy")
        assert [r.internal_id for r in buy_only] == ["B2"]
        limited = await latest_predictions(s, limit=1)
        assert len(limited) == 1 and limited[0].internal_id == "B2"


async def test_repo_predictions_for_bond_ordering():
    p1 = _pred("B1", date(2026, 1, 1), "v1")
    p2 = _pred("B1", date(2026, 1, 5), "v1")
    p3 = _pred("B2", date(2026, 1, 5), "v1")
    async with session_scope() as s:
        await upsert_predictions(s, [p1, p2, p3])
    async with session_scope() as s:
        rows = await predictions_for_bond(s, "B1")
        assert [r.asof_date for r in rows] == [date(2026, 1, 5), date(2026, 1, 1)]
        assert await predictions_for_bond(s, "B3") == []


# --------------------------------------------------------------------------- #
# monitoring/metrics.py
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_metrics(monkeypatch):
    """Isolate the module-level _metrics dict for every test."""
    fresh = dict(metrics_mod._metrics)
    monkeypatch.setattr(metrics_mod, "_metrics", fresh)
    yield


def test_inc_existing_key():
    metrics_mod.inc("scrape_total")
    assert metrics_mod.get_metrics()["scrape_total"] == 1
    metrics_mod.inc("scrape_total", 3)
    assert metrics_mod.get_metrics()["scrape_total"] == 4


def test_inc_unknown_key_creates_it():
    metrics_mod.inc("new_counter")
    assert metrics_mod.get_metrics()["new_counter"] == 1
    metrics_mod.inc("new_counter", 2)
    assert metrics_mod.get_metrics()["new_counter"] == 3


def test_inc_float_value():
    metrics_mod.inc("latency", 0.5)
    metrics_mod.inc("latency", 0.25)
    assert metrics_mod.get_metrics()["latency"] == 0.75


def test_inc_on_non_numeric_value_falls_back_to_zero():
    metrics_mod.set_metric("weird", {"a": 1})
    metrics_mod.inc("weird")
    assert metrics_mod.get_metrics()["weird"] == 1


def test_set_metric_overwrites():
    metrics_mod.set_metric("api_requests", 5)
    metrics_mod.set_metric("api_requests", 9)
    assert metrics_mod.get_metrics()["api_requests"] == 9


def test_get_metrics_returns_copy_with_all_keys_and_uptime():
    got = metrics_mod.get_metrics()
    assert got["uptime_seconds"] >= 0
    for key in (
        "scrape_total",
        "scrape_errors",
        "api_requests",
        "api_errors",
        "bot_commands",
        "bot_errors",
        "last_scrape_duration_ms",
        "last_scrape_at",
        "bonds_total",
        "started_at",
        "uptime_seconds",
    ):
        assert key in got
    got["scrape_total"] = 999  # mutation must not leak back into module state
    assert metrics_mod.get_metrics()["scrape_total"] == 0


def test_bad_started_at_falls_back_to_now():
    metrics_mod.set_metric("started_at", "not-a-number")
    uptime = metrics_mod.get_metrics()["uptime_seconds"]
    assert abs(uptime) < 1e-3  # time.time() sampled twice -> ~0, up to float jitter


def test_timed_decorator_sets_duration_on_success():
    @metrics_mod.timed("work")
    def do_work(x: int) -> int:
        return x * 2

    assert do_work(3) == 6
    d = metrics_mod.get_metrics()["last_work_duration_ms"]
    assert isinstance(d, (int, float)) and d >= 0


def test_timed_decorator_sets_duration_and_reraises_on_exception():
    @metrics_mod.timed("boom")
    def boom():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        boom()
    assert "last_boom_duration_ms" in metrics_mod.get_metrics()


async def test_timed_async_returns_result_and_sets_duration():
    async def coro(x: int) -> int:
        return x + 1

    result = await metrics_mod.timed_async("async_work", coro(1))
    assert result == 2
    d = metrics_mod.get_metrics()["last_async_work_duration_ms"]
    assert isinstance(d, (int, float)) and d >= 0


async def test_timed_async_sets_duration_and_propagates_exception():
    async def bad():
        raise ValueError("bad")

    with pytest.raises(ValueError):
        await metrics_mod.timed_async("async_bad", bad())
    assert "last_async_bad_duration_ms" in metrics_mod.get_metrics()


# --------------------------------------------------------------------------- #
# monitoring/engine.py
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _no_partner_webhook(monkeypatch):
    """Stub the partner webhook so monitoring tests never touch the network."""
    import notifications.delivery as delivery

    async def _noop(*args, **kwargs) -> int:
        return 0

    monkeypatch.setattr(delivery, "emit_partner_alert", _noop)


@pytest.fixture(autouse=True)
async def _clean_db():
    """The in-memory engine is shared process-wide; wipe every table so each
    test starts from an empty database."""
    from contextlib import suppress

    from sqlalchemy import delete
    from sqlalchemy.exc import OperationalError

    from scraper.db import get_engine
    from scraper.orm import Base

    engine = get_engine()
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            with suppress(OperationalError):  # table not created yet (ordering safety)
                await conn.execute(delete(table))
    yield


def test_pct_change_formula():
    assert mon_engine._pct_change(100, 110) == 10.0
    assert mon_engine._pct_change(5, 4) == -20.0
    assert mon_engine._pct_change(0, 5) == 0.0  # non-positive baseline -> no signal
    assert mon_engine._pct_change(-3, 6) == 0.0


def test_assess_data_quality_naive_timestamps_treated_as_utc():
    now = datetime.now(UTC)
    naive = now.replace(tzinfo=None)
    from monitoring.engine import assess_data_quality

    class _B:
        status = "active"
        yield_to_maturity = 8.0
        fetched_at = naive

    report = assess_data_quality([_B()], now=now)
    assert report.stale_hours is not None and 0 <= report.stale_hours < 1
    assert report.issues == []


async def _add_active_bond(
    s, iid, *, ytm="8.0", coupon="5.0", price="100.0", status="active", offer_date=None
):
    s.add(
        BondORM(
            internal_id=iid,
            name=f"Bond {iid}",
            currency="USD",
            status=status,
            yield_to_maturity=Decimal(ytm),
            coupon_rate=Decimal(coupon),
            price=Decimal(price),
            offer_date=offer_date,
        )
    )


async def _add_history(s, iid, day, *, ytm="8.0", coupon="5.0", price="100.0"):
    s.add(
        BondHistoryORM(
            internal_id=iid,
            date=day,
            yield_=Decimal(ytm),
            coupon=Decimal(coupon),
            price=Decimal(price),
        )
    )


async def test_detect_bond_changes_yield_drop():
    async with session_scope() as s:
        await _add_active_bond(s, "B1", ytm="8.0")
        await _add_history(s, "B1", date.today() - timedelta(days=1), ytm="9.0")
    async with session_scope() as s:
        res = await mon_engine.detect_bond_changes(s)
    assert res.new_alerts == 1
    assert res.by_kind == {"yield_drop": 1}


async def test_detect_bond_changes_yield_rise():
    async with session_scope() as s:
        await _add_active_bond(s, "B1", ytm="9.0")
        await _add_history(s, "B1", date.today() - timedelta(days=1), ytm="8.0")
    async with session_scope() as s:
        res = await mon_engine.detect_bond_changes(s)
    assert res.by_kind == {"yield_rise": 1}


async def test_detect_bond_changes_no_move_no_alert():
    async with session_scope() as s:
        await _add_active_bond(s, "B1", ytm="8.0")
        await _add_history(s, "B1", date.today() - timedelta(days=1), ytm="8.1")
    async with session_scope() as s:
        res = await mon_engine.detect_bond_changes(s)
    assert res.new_alerts == 0
    assert res.by_kind == {}


async def test_detect_bond_changes_coupon_change():
    async with session_scope() as s:
        await _add_active_bond(s, "B1", coupon="5.5")
        await _add_history(s, "B1", date.today() - timedelta(days=1), coupon="5.0")
    async with session_scope() as s:
        res = await mon_engine.detect_bond_changes(s)
    assert res.by_kind == {"coupon_change": 1}


async def test_detect_bond_changes_price_change():
    async with session_scope() as s:
        await _add_active_bond(s, "B1", price="99.0")
        await _add_history(s, "B1", date.today() - timedelta(days=1), price="100.0")
    async with session_scope() as s:
        res = await mon_engine.detect_bond_changes(s)
    assert res.by_kind == {"price_change": 1}


async def test_detect_bond_changes_high_score():
    async with session_scope() as s:
        await _add_active_bond(s, "B1")
        s.add(BondScoreORM(internal_id="B1", score=Decimal("95"), breakdown={}))
    async with session_scope() as s:
        res = await mon_engine.detect_bond_changes(s)
    assert res.by_kind == {"high_score": 1}


async def test_detect_bond_changes_matured_and_offer():
    async with session_scope() as s:
        await _add_active_bond(s, "B1", status="matured")
        await _add_active_bond(s, "B2", offer_date=date.today())
    async with session_scope() as s:
        res = await mon_engine.detect_bond_changes(s)
    assert res.by_kind == {"matured": 1, "offer": 1}
    assert res.new_alerts == 2


async def test_detect_bond_changes_dedup_second_run_silent():
    async with session_scope() as s:
        await _add_active_bond(s, "B1", ytm="8.0")
        await _add_history(s, "B1", date.today() - timedelta(days=1), ytm="9.0")
    async with session_scope() as s:
        first = await mon_engine.detect_bond_changes(s)
        second = await mon_engine.detect_bond_changes(s)
    assert first.new_alerts == 1
    assert second.new_alerts == 0
    assert second.by_kind == {}


async def test_detect_fx_changes_big_move_alerts():
    async with session_scope() as s:
        s.add(FxRateORM(pair="USD/BYN", rate=Decimal("3.0"), observed_at=datetime(2026, 1, 1)))
        s.add(FxRateORM(pair="USD/BYN", rate=Decimal("3.30"), observed_at=datetime(2026, 1, 2)))
        s.add(FxRateORM(pair="EUR/BYN", rate=Decimal("3.5"), observed_at=datetime(2026, 1, 1)))
        s.add(FxRateORM(pair="EUR/BYN", rate=Decimal("3.6"), observed_at=datetime(2026, 1, 2)))
    async with session_scope() as s:
        res = await mon_engine.detect_fx_changes(s)
    assert res.by_kind == {"fx_usd_byn": 1, "fx_eur_byn": 1}
    assert res.new_alerts == 2


async def test_detect_fx_changes_small_move_no_alert():
    async with session_scope() as s:
        s.add(FxRateORM(pair="USD/BYN", rate=Decimal("3.0"), observed_at=datetime(2026, 1, 1)))
        s.add(FxRateORM(pair="USD/BYN", rate=Decimal("3.004"), observed_at=datetime(2026, 1, 2)))
    async with session_scope() as s:
        res = await mon_engine.detect_fx_changes(s)
    assert res.new_alerts == 0
    assert res.by_kind == {}


async def test_detect_fx_changes_single_row_no_previous():
    async with session_scope() as s:
        s.add(FxRateORM(pair="USD/BYN", rate=Decimal("3.0"), observed_at=datetime(2026, 1, 1)))
    async with session_scope() as s:
        res = await mon_engine.detect_fx_changes(s)
    assert res.new_alerts == 0


async def test_detect_metal_changes():
    async with session_scope() as s:
        s.add(MetalPriceORM(metal="XAU", price=Decimal("2400"), observed_at=datetime(2026, 1, 1)))
        s.add(MetalPriceORM(metal="XAU", price=Decimal("2600"), observed_at=datetime(2026, 1, 2)))
    async with session_scope() as s:
        res = await mon_engine.detect_metal_changes(s)
    assert res.by_kind == {"metal_xau": 1}


async def test_data_source_health_ok():
    async with session_scope() as s:
        await _add_active_bond(s, "B1")
        row = (await s.execute(__import__("sqlalchemy").select(BondORM))).scalars().one()
        row.fetched_at = datetime.now(UTC) - timedelta(hours=1)
    async with session_scope() as s:
        h = await mon_engine.data_source_health(s)
    assert h["status"] == "ok"
    assert h["total"] == 1 and h["active"] == 1
    assert h["empty_ytm_pct"] == 0.0
    assert h["latest_fetch"] is not None
    assert h["issues"] == []


async def test_data_source_health_empty_db_is_down():
    async with session_scope() as s:
        h = await mon_engine.data_source_health(s)
    assert h["status"] == "down"
    assert h["total"] == 0
    assert h["latest_fetch"] is None
    assert h["issues"]


async def test_data_source_health_stale_is_degraded():
    async with session_scope() as s:
        await _add_active_bond(s, "B1")
        row = (await s.execute(__import__("sqlalchemy").select(BondORM))).scalars().one()
        row.fetched_at = datetime.now(UTC) - timedelta(hours=100)
    async with session_scope() as s:
        h = await mon_engine.data_source_health(s)
    assert h["status"] == "degraded"
    assert h["stale_hours"] >= 100
    assert any("устарели" in i for i in h["issues"])


async def test_detect_data_quality_stale_data_alerts():
    async with session_scope() as s:
        await _add_active_bond(s, "B1")
        row = (await s.execute(__import__("sqlalchemy").select(BondORM))).scalars().one()
        row.fetched_at = datetime.now(UTC) - timedelta(hours=100)
    async with session_scope() as s:
        res = await mon_engine.detect_data_quality(s)
    assert res.by_kind == {"data_quality": 1}
    assert res.new_alerts == 1


async def test_detect_data_quality_empty_db_alerts_no_fetches():
    async with session_scope() as s:
        res = await mon_engine.detect_data_quality(s)
    assert res.new_alerts == 1  # "нет ни одной облигации с датой обновления"


async def test_run_all_structure_with_empty_db():
    async with session_scope() as s:
        results = await mon_engine.run_all(s)
    assert set(results) == {"bonds", "fx", "metals", "data_quality"}
    for _name, mr in results.items():
        assert isinstance(mr, mon_engine.MonitoringResult)
        assert isinstance(mr.new_alerts, int)
    assert results["bonds"].new_alerts == 0
    assert results["fx"].new_alerts == 0
    assert results["metals"].new_alerts == 0
    assert results["data_quality"].new_alerts == 1


async def test_run_all_isolates_failing_check(monkeypatch):
    async def _boom(session):
        raise RuntimeError("boom")

    monkeypatch.setattr(mon_engine, "detect_metal_changes", _boom)
    async with session_scope() as s:
        results = await mon_engine.run_all(s)
    assert results["metals"].new_alerts == 0
    assert results["metals"].by_kind == {}
    assert "bonds" in results and "fx" in results and "data_quality" in results


# --------------------------------------------------------------------------- #
# forecast/engine.py
# --------------------------------------------------------------------------- #


def test_monthly_return_formula():
    assert fc._monthly_return(7.0) == Decimal(str((1.07) ** (1 / 12) - 1))
    assert fc._monthly_return(0.0) == Decimal("0")
    assert fc._monthly_return(-5.0) == Decimal(str((0.95) ** (1 / 12) - 1))


def test_annuity_formula():
    r = Decimal(str((1.07) ** (1 / 12) - 1))
    one_month = Decimal("10000") * (Decimal("1") + r) + Decimal("500")
    assert fc._annuity(Decimal("10000"), Decimal("500"), 7.0, 1) == one_month
    twelve = fc._annuity(Decimal("10000"), Decimal("500"), 7.0, 12)
    assert twelve == pytest.approx(Decimal("16890.14857275570"), abs=Decimal("0.0001"))


def test_forecast_capital_deterministic_path():
    res = fc.forecast_capital(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("500"),
        expected_annual_return_pct=7.0,
        horizon_years=1,
        volatility_pct=0.0,
    )
    r = Decimal(str((1.07) ** (1 / 12) - 1))
    expected = (
        Decimal("10000") * (Decimal("1") + r) ** 12
        + Decimal("500") * ((Decimal("1") + r) ** 12 - Decimal("1")) / r
    )
    assert float(res.expected_capital) == pytest.approx(float(expected), abs=0.01)
    assert res.pessimistic_capital == res.expected_capital
    assert res.optimistic_capital == res.expected_capital
    assert res.mc_percentiles == {}
    assert res.cvar_95 is None
    assert res.assumptions["method"] == "deterministic"
    assert res.horizon_years == 1


def test_forecast_capital_zero_contribution_compounds_initial():
    res = fc.forecast_capital(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("0"),
        expected_annual_return_pct=7.0,
        horizon_years=1,
        volatility_pct=0.0,
    )
    r = Decimal(str((1.07) ** (1 / 12) - 1))
    assert float(res.expected_capital) == pytest.approx(
        10000.0 * float((Decimal("1") + r) ** 12), abs=0.01
    )


def test_forecast_capital_volatility_percentiles_and_cvar():
    a = fc.forecast_capital(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("500"),
        expected_annual_return_pct=7.0,
        horizon_years=1,
        volatility_pct=4.0,
        n_paths=500,
    )
    b = fc.forecast_capital(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("500"),
        expected_annual_return_pct=7.0,
        horizon_years=1,
        volatility_pct=4.0,
        n_paths=500,
    )
    assert set(a.mc_percentiles) == {"p5", "p25", "p50", "p75", "p95"}
    assert a.pessimistic_capital == a.mc_percentiles["p5"]
    assert a.optimistic_capital == a.mc_percentiles["p95"]
    assert a.cvar_95 is not None
    assert a.cvar_95 <= a.mc_percentiles["p5"]
    assert a.assumptions["method"] == "monte_carlo"
    assert a.expected_capital == b.expected_capital  # deterministic given _MC_SEED
    assert a.mc_percentiles == b.mc_percentiles
    assert a.cvar_95 == b.cvar_95


def test_monte_carlo_shape_and_determinism():
    finals, means = fc._monte_carlo(Decimal("10000"), Decimal("500"), 7.0, 4.0, 12, n_paths=200)
    assert len(finals) == 200
    assert len(means) == 1
    assert finals == sorted(finals)
    finals2, _ = fc._monte_carlo(Decimal("10000"), Decimal("500"), 7.0, 4.0, 12, n_paths=200)
    assert finals == finals2


def test_monte_carlo_zero_volatility_all_paths_equal():
    finals, _means = fc._monte_carlo(Decimal("10000"), Decimal("0"), 7.0, 0.0, 12, n_paths=100)
    assert all(f == finals[0] for f in finals)
    # cvar_95 of this degenerate distribution is exactly the path value.
    assert finals[0] == pytest.approx(10000 * (1.07) ** (12 / 12), abs=1.0)


def test_forecast_horizons_structure_and_growth():
    horizons = fc.forecast_horizons(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("500"),
        expected_annual_return_pct=7.0,
        volatility_pct=4.0,
    )
    assert [h.horizon_years for h in horizons] == [1, 3, 5]
    assert len(horizons) == 3
    capitals = [h.expected_capital for h in horizons]
    assert capitals == sorted(capitals)
    assert capitals[0] < capitals[1] < capitals[2]
    r = Decimal(str((1.07) ** (1 / 12) - 1))
    expected_1y = (
        Decimal("10000") * (Decimal("1") + r) ** 12
        + Decimal("500") * ((Decimal("1") + r) ** 12 - Decimal("1")) / r
    )
    assert float(horizons[0].expected_capital) == pytest.approx(float(expected_1y), abs=0.01)


def test_forecast_horizons_negative_return_capital_below_contributions():
    horizons = fc.forecast_horizons(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("500"),
        expected_annual_return_pct=-5.0,
        volatility_pct=0.0,
    )
    assert horizons[0].expected_capital < Decimal("10000") + Decimal("500") * 12
    assert horizons[0].expected_capital < horizons[1].expected_capital


def test_forecast_capital_zero_volatility_percentiles_collapse():
    res = fc.forecast_capital(
        initial_capital=Decimal("10000"),
        monthly_contribution=Decimal("500"),
        expected_annual_return_pct=7.0,
        horizon_years=5,
        volatility_pct=0.0,
    )
    assert res.pessimistic_capital == res.expected_capital
    assert res.optimistic_capital == res.expected_capital
    assert res.mc_percentiles == {}
    assert res.cvar_95 is None


# KNOWN-FAILING: the source does not guard annual return < -100. Python
# returns a complex for (-0.5) ** (1/12) and Decimal(str(complex)) raises
# decimal.InvalidOperation (an ArithmeticError), so ValueError is never raised.
def test_forecast_capital_annual_return_below_minus_100_raises():
    with pytest.raises(ValueError):
        fc.forecast_capital(
            initial_capital=Decimal("10000"),
            monthly_contribution=Decimal("500"),
            expected_annual_return_pct=-150.0,
            horizon_years=1,
            volatility_pct=0.0,
        )


async def test_monitoring_alerts_persisted_to_db():
    """End-to-end: a detected alert lands in the alerts table."""
    async with session_scope() as s:
        await _add_active_bond(s, "B1", ytm="8.0")
        await _add_history(s, "B1", date.today() - timedelta(days=1), ytm="9.0")
    async with session_scope() as s:
        res = await mon_engine.detect_bond_changes(s)
        assert res.new_alerts == 1
    from sqlalchemy import select

    async with session_scope() as s:
        alerts = list((await s.execute(select(AlertORM))).scalars().all())
        assert len(alerts) == 1
        assert alerts[0].kind == "yield_drop"
        assert alerts[0].internal_id == "B1"
