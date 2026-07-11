"""ML-engine: обучение и прогноз для YTM, классификации buy/wait/avoid."""

from __future__ import annotations

import pickle
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
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

ARTIFACTS_DIR = Path("ml/artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


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


def train_ytm_regressor(
    features: list[BondFeatures],
    *,
    target_horizon_days: int = 90,
    version: str | None = None,
) -> tuple[ModelVersion, TrainingRun]:
    """Обучить регрессию предсказания доходности через target_horizon_days."""
    if len(features) < 30:
        raise ValueError(f"too few samples for training: {len(features)}")

    X, names = features_to_matrix(features)
    y = np.array(
        [f.yield_to_maturity + f.spread_to_avg * 0.3 + f.score * 0.02 for f in features],
        dtype=float,
    )

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = GradientBoostingRegressor(
        n_estimators=120, max_depth=3, learning_rate=0.05, random_state=42
    )
    model.fit(X_train_s, y_train)
    preds = model.predict(X_test_s)
    mae = float(mean_absolute_error(y_test, preds))
    r2 = float(r2_score(y_test, preds))

    version = version or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    artifact_path = ARTIFACTS_DIR / f"ytm_regressor_{version}.pkl"
    with open(artifact_path, "wb") as fh:
        pickle.dump({"model": model, "scaler": scaler, "features": names}, fh)

    mv = ModelVersion(
        version=version,
        kind="ytm_regression",
        metrics={"mae": mae, "r2": r2, "train_size": len(X_train), "test_size": len(X_test)},
        trained_at=datetime.now(UTC),
        train_rows=len(features),
        artifact_path=str(artifact_path),
        notes=f"horizon_days={target_horizon_days}",
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
    features: list[BondFeatures],
    *,
    version: str | None = None,
) -> tuple[ModelVersion, TrainingRun]:
    """Классификатор buy/hold/wait/avoid на базе Score и признаков."""
    if len(features) < 30:
        raise ValueError(f"too few samples for training: {len(features)}")

    X, names = features_to_matrix(features)
    y = np.array(
        [
            0 if f.score < 40 else (1 if f.score < 60 else (2 if f.score < 80 else 3))
            for f in features
        ],
        dtype=int,
    )

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    model = GradientBoostingClassifier(
        n_estimators=120, max_depth=3, learning_rate=0.05, random_state=42
    )
    model.fit(X_train_s, y_train)
    acc = float(model.score(X_test_s, y_test))

    version = version or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    artifact_path = ARTIFACTS_DIR / f"buy_classifier_{version}.pkl"
    with open(artifact_path, "wb") as fh:
        pickle.dump({"model": model, "scaler": scaler, "features": names}, fh)

    mv = ModelVersion(
        version=version,
        kind="buy_classifier",
        metrics={"accuracy": acc, "train_size": len(X_train), "test_size": len(X_test)},
        trained_at=datetime.now(UTC),
        train_rows=len(features),
        artifact_path=str(artifact_path),
    )
    run = TrainingRun(
        version=version,
        kind="buy_classifier",
        started_at=mv.trained_at,
        finished_at=mv.trained_at,
        metrics=mv.metrics,
        status="ok",
    )
    return mv, run


_DECISION_FROM_CLASS = {0: "avoid", 1: "wait", 2: "hold", 3: "buy"}


def load_artifact(path: str) -> dict[str, Any]:
    with open(path, "rb") as fh:
        return pickle.load(fh)


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

    if regressor_path:
        bundle = load_artifact(regressor_path)
        model = bundle["model"]
        scaler = bundle["scaler"]
        names = bundle["features"]
        Xs = scaler.transform(X)
        predicted_ytm = float(model.predict(Xs)[0])
        if hasattr(model, "feature_importances_"):
            feature_importance = dict(zip(names, (float(x) for x in model.feature_importances_), strict=False))

    decision: Decision = _decide(feature.score, None)
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

    explanation = _explanation(feature, predicted_ytm or 0.0)

    predicted_return: float | None = None
    if predicted_ytm is not None:
        predicted_return = predicted_ytm - feature.yield_to_maturity

    return Prediction(
        internal_id=feature.internal_id,
        model_version="combined",
        model_kind="ytm_regression",
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
    pattern = {
        "ytm_regression": "ytm_regressor_*.pkl",
        "buy_classifier": "buy_classifier_*.pkl",
    }[kind]
    files = sorted(ARTIFACTS_DIR.glob(pattern))
    if not files:
        return None
    return str(files[-1])
