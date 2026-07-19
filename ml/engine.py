"""ML-engine: обучение и прогноз для YTM, классификации buy/wait/avoid."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler

from ml.features import features_to_matrix
from ml.models import (
    BondFeatures,
    Decision,
    ModelKind,
    ModelVersion,
    Prediction,
    TrainingRun,
)
from ml.registry import (
    ARTIFACTS_DIR,
    load_artifact_cached,
    save_artifact,
)

ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def _version_from_path(path: str | None) -> str | None:
    """Extract the artifact version from an artifact path, or None."""
    if not path:
        return None
    name = Path(path).stem  # e.g. ytm_regressor_20240101120000
    for prefix in ("ytm_regressor_", "buy_classifier_", "volatility_"):
        if name.startswith(prefix):
            return name[len(prefix):]
    return None


def _decide(score: float, predicted_return: float | None) -> Decision:
    if score < 40:
        return "avoid"
    if predicted_return is not None and predicted_return < 0:
        return "wait"
    if score >= 75 and (predicted_return is None or predicted_return >= 2):
        return "buy"
    return "hold"


def _explanation(features: BondFeatures, predicted_ytm: float) -> list[str]:
    notes: list[str] = []
    if features.spread_to_avg > 1.0:
        notes.append(f"доходность выше средней по валюте на {features.spread_to_avg:.2f}%")
    if features.score >= 75:
        notes.append(f"высокий Reward/Risk Score ({features.score:.0f})")
    if features.duration_years <= 2:
        notes.append("короткая дюрация — меньше процентного риска")
    if features.score_metal_component > 0:
        notes.append("дополнительный бонус за металлы")
    if features.is_gov_issuer:
        notes.append("эмитент — государство/министерство финансов")
    if features.yield_momentum_30d < -0.05:
        notes.append("доходность за месяц снизилась — возможно, рост цены")
    if features.yield_momentum_30d > 0.05:
        notes.append("доходность за месяц выросла — рынок переоценивает риск")
    if predicted_ytm:
        notes.append(f"прогноз YTM: {predicted_ytm:.2f}%")
    return notes


def _time_split(
    samples: list[Any], test_fraction: float = 0.25
) -> tuple[list[Any], list[Any]]:
    """Walk-forward split: train on the earlier samples, validate on the latest.

    Financial series must never be shuffled — a random split leaks future
    information into training. We sort by ``asof`` and hold out the most recent
    ``test_fraction`` as an out-of-time validation set.
    """
    ordered = sorted(samples, key=lambda s: s.asof)
    cut = int(len(ordered) * (1 - test_fraction))
    cut = max(1, min(cut, len(ordered) - 1))
    return ordered[:cut], ordered[cut:]


def train_ytm_regressor(
    samples: list[Any] | None = None,
    *,
    target_horizon_days: int = 90,
    version: str | None = None,
    features: list[BondFeatures] | None = None,  # noqa: ARG001  # deprecated, kept for callers
) -> tuple[ModelVersion, TrainingRun]:
    """Train a YTM forecaster on leakage-free future targets.

    ``samples`` are :class:`ml.features.TrainingSample` objects pairing features
    observed at ``asof`` with the YTM actually realized ``horizon_days`` later.
    The split is walk-forward (out-of-time), so the reported metrics reflect
    genuine predictive skill rather than memorised identities.
    """
    if not samples:
        raise ValueError(
            "train_ytm_regressor requires leakage-free TrainingSample list; "
            "build them via ml.features.build_training_samples()"
        )
    if len(samples) < 30:
        raise ValueError(f"too few samples for training: {len(samples)}")

    train_s, test_s = _time_split(samples)

    X_train, names = features_to_matrix([s.features for s in train_s])
    X_test, _ = features_to_matrix([s.features for s in test_s])
    y_train = np.array([s.future_ytm for s in train_s], dtype=float)
    y_test = np.array([s.future_ytm for s in test_s], dtype=float)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = GradientBoostingRegressor(
        n_estimators=120, max_depth=3, learning_rate=0.05, random_state=42
    )
    model.fit(X_train_s, y_train)
    preds = model.predict(X_test_s)
    mae = float(mean_absolute_error(y_test, preds))
    r2 = float(r2_score(y_test, preds)) if len(set(y_test.tolist())) > 1 else 0.0

    # Naive baseline: "future YTM == current YTM" (random walk). A useful model
    # must beat this; we record the comparison so degradation is visible.
    current_ytm_test = np.array([s.features.yield_to_maturity for s in test_s], dtype=float)
    baseline_mae = float(mean_absolute_error(y_test, current_ytm_test))

    version = version or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    artifact_path = ARTIFACTS_DIR / f"ytm_regressor_{version}.joblib"
    save_artifact(artifact_path, {"model": model, "scaler": scaler, "features": names})

    mv = ModelVersion(
        version=version,
        kind="ytm_regression",
        metrics={
            "mae": mae,
            "r2": r2,
            "baseline_mae": baseline_mae,
            "beats_baseline": 1.0 if mae < baseline_mae else 0.0,
            "train_size": len(train_s),
            "test_size": len(test_s),
        },
        trained_at=datetime.now(UTC),
        train_rows=len(samples),
        artifact_path=str(artifact_path),
        notes=f"horizon_days={target_horizon_days}; walk-forward split",
    )
    run = TrainingRun(
        version=version,
        kind="ytm_regression",
        started_at=mv.trained_at,
        finished_at=mv.trained_at,
        metrics=mv.metrics,
        status="ok",
        notes=mv.notes,
    )
    return mv, run


def train_buy_classifier(
    samples: list[Any] | None = None,
    *,
    version: str | None = None,
    buy_threshold_pct: float = -0.25,
    avoid_threshold_pct: float = 0.5,
    features: list[BondFeatures] | None = None,  # noqa: ARG001  # deprecated, kept for callers
) -> tuple[ModelVersion, TrainingRun]:
    """Train a buy/hold/avoid classifier on *realized* future outcomes.

    The label is derived from the future YTM move, not from the current Score
    (which is itself an input feature — using it as the label was circular).
    A falling future YTM means the price rose ⇒ "buy"; a sharp rise ⇒ "avoid".
    """
    if not samples:
        raise ValueError(
            "train_buy_classifier requires leakage-free TrainingSample list; "
            "build them via ml.features.build_training_samples()"
        )
    if len(samples) < 30:
        raise ValueError(f"too few samples for training: {len(samples)}")

    def _label(move: float) -> int:
        # move = future_ytm - current_ytm (percentage points)
        if move <= buy_threshold_pct:
            return 2  # yield fell -> price rose -> buy
        if move >= avoid_threshold_pct:
            return 0  # yield rose -> price fell -> avoid
        return 1  # roughly flat -> hold

    train_s, test_s = _time_split(samples)

    X_train, names = features_to_matrix([s.features for s in train_s])
    X_test, _ = features_to_matrix([s.features for s in test_s])
    y_train = np.array([_label(s.future_return_pct) for s in train_s], dtype=int)
    y_test = np.array([_label(s.future_return_pct) for s in test_s], dtype=int)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = GradientBoostingClassifier(
        n_estimators=120, max_depth=3, learning_rate=0.05, random_state=42
    )
    # Guard against a degenerate single-class training slice.
    if len(set(y_train.tolist())) < 2:
        raise ValueError("training slice has a single outcome class; need more history")
    model.fit(X_train_s, y_train)
    acc = float(model.score(X_test_s, y_test)) if len(test_s) else 0.0
    # Majority-class baseline for context.
    if len(y_test):
        _vals, counts = np.unique(y_test, return_counts=True)
        baseline_acc = float(counts.max() / counts.sum())
    else:
        baseline_acc = 0.0

    version = version or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    artifact_path = ARTIFACTS_DIR / f"buy_classifier_{version}.joblib"
    save_artifact(artifact_path, {"model": model, "scaler": scaler, "features": names})

    mv = ModelVersion(
        version=version,
        kind="buy_classifier",
        metrics={
            "accuracy": acc,
            "baseline_accuracy": baseline_acc,
            "beats_baseline": 1.0 if acc > baseline_acc else 0.0,
            "train_size": len(train_s),
            "test_size": len(test_s),
        },
        trained_at=datetime.now(UTC),
        train_rows=len(samples),
        artifact_path=str(artifact_path),
        notes="label=realized future YTM move; walk-forward split",
    )
    run = TrainingRun(
        version=version,
        kind="buy_classifier",
        started_at=mv.trained_at,
        finished_at=mv.trained_at,
        metrics=mv.metrics,
        status="ok",
        notes=mv.notes,
    )
    return mv, run


# Class labels produced by ``train_buy_classifier`` (realized future YTM move).
_DECISION_FROM_CLASS = {0: "avoid", 1: "hold", 2: "buy"}


def load_artifact(path: str) -> dict[str, Any]:
    """Backward-compatible alias for the cached artifact loader."""
    return load_artifact_cached(path)


def predict_one(
    feature: BondFeatures,
    *,
    regressor_path: str | None,
    classifier_path: str | None,
) -> Prediction:
    """Сделать прогноз по одной облигации (используется обе модели)."""
    X, _ = features_to_matrix([feature])

    predicted_ytm: float | None = None
    feature_importance: dict[str, float] = {}
    used_reg = False
    used_cls = False

    if regressor_path:
        bundle = load_artifact(regressor_path)
        model = bundle["model"]
        scaler = bundle["scaler"]
        names = bundle["features"]
        Xs = scaler.transform(X)
        predicted_ytm = float(model.predict(Xs)[0])
        if hasattr(model, "feature_importances_"):
            feature_importance = dict(zip(names, (float(x) for x in model.feature_importances_), strict=False))
        used_reg = True

    predicted_return: float | None = (
        predicted_ytm - feature.yield_to_maturity if predicted_ytm is not None else None
    )

    decision: Decision = _decide(feature.score, predicted_return)
    confidence = min(max(feature.score / 100, 0.0), 1.0)

    if classifier_path:
        bundle = load_artifact(classifier_path)
        model = bundle["model"]
        scaler = bundle["scaler"]
        names = bundle["features"]
        Xs = scaler.transform(X)
        proba = model.predict_proba(Xs)[0]
        classes = list(model.classes_)
        best_class = int(classes[int(np.argmax(proba))])
        decision = _DECISION_FROM_CLASS.get(best_class, decision)
        confidence = float(np.max(proba))
        used_cls = True

    # Label the prediction by the model(s) that actually produced it instead of
    # hard-coding a single kind (previously always "ytm_regression" even when the
    # classifier supplied the decision).
    if used_reg and used_cls:
        model_kind: ModelKind = "combined"
    elif used_cls:
        model_kind = "buy_classifier"
    else:
        model_kind = "ytm_regression"

    model_version = _version_from_path(regressor_path) if used_reg else (
        _version_from_path(classifier_path) or "combined"
    )

    explanation = _explanation(feature, predicted_ytm or 0.0)

    return Prediction(
        internal_id=feature.internal_id,
        model_version=model_version,
        model_kind=model_kind,
        asof_date=feature.asof_date,
        predicted_ytm=predicted_ytm,
        predicted_return_pct=predicted_return,
        decision=decision,
        confidence=round(confidence, 3),
        feature_importance=dict(sorted(feature_importance.items(), key=lambda x: -x[1])[:10]),
        explanation=explanation,
        created_at=datetime.now(UTC),
    )


def predict_batch(
    features: list[BondFeatures],
    *,
    regressor_path: str | None,
    classifier_path: str | None,
) -> list[Prediction]:
    return [
        predict_one(
            f,
            regressor_path=regressor_path,
            classifier_path=classifier_path,
        )
        for f in features
    ]


def latest_artifact(kind: ModelKind) -> str | None:
    from ml.registry import latest_artifact as _latest

    return _latest(kind)
