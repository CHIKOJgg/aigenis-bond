"""ML: feature engineering, обучение, прогноз."""

from __future__ import annotations

from ml.engine import (
    ARTIFACTS_DIR,
    latest_artifact,
    load_artifact,
    predict_batch,
    predict_one,
    train_buy_classifier,
    train_ytm_regressor,
)
from ml.features import build_dataset, build_features, features_to_matrix
from ml.models import (
    BondFeatures,
    Decision,
    ModelKind,
    ModelVersion,
    Prediction,
    RebalanceAction,
    RebalancePlan,
    Recommendation,
    TrainingRun,
)

__all__ = [
    "ARTIFACTS_DIR",
    "BondFeatures",
    "Decision",
    "ModelKind",
    "ModelVersion",
    "Prediction",
    "RebalanceAction",
    "RebalancePlan",
    "Recommendation",
    "TrainingRun",
    "build_dataset",
    "build_features",
    "features_to_matrix",
    "latest_artifact",
    "load_artifact",
    "predict_batch",
    "predict_one",
    "train_buy_classifier",
    "train_ytm_regressor",
]
