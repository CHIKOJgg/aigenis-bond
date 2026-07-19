"""Модели V3: ML-прогноз, рекомендации, auto-rebalance."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Decision = Literal["buy", "hold", "wait", "avoid"]
ModelKind = Literal["ytm_regression", "buy_classifier", "volatility"]


class BondFeatures(BaseModel):
    """Признаки облигации для ML-модели."""

    model_config = ConfigDict(extra="ignore")

    internal_id: str
    asof_date: date

    currency_idx: int
    duration_years: float
    days_to_maturity: float
    modified_duration: float = 0.0
    coupon_rate: float
    price: float
    yield_to_maturity: float
    spread_to_avg: float

    rolling_yield_mean_30d: float
    rolling_yield_std_30d: float
    yield_momentum_30d: float
    price_momentum_30d: float

    score: float
    score_yield_component: float
    score_currency_component: float
    score_duration_component: float
    score_metal_component: float

    is_gov_issuer: int
    is_active: int


class Prediction(BaseModel):
    """Прогноз по облигации."""

    model_config = ConfigDict(extra="ignore")

    internal_id: str
    model_version: str
    model_kind: ModelKind
    asof_date: date

    predicted_ytm: float | None = None
    predicted_return_pct: float | None = None
    predicted_volatility: float | None = None
    decision: Decision | None = None
    confidence: float

    feature_importance: dict[str, float] = Field(default_factory=dict)
    explanation: list[str] = Field(default_factory=list)
    created_at: datetime


class ModelVersion(BaseModel):
    """Версия модели."""

    model_config = ConfigDict(extra="ignore")

    version: str
    kind: ModelKind
    metrics: dict[str, float]
    trained_at: datetime
    train_rows: int
    artifact_path: str
    notes: str = ""


class TrainingRun(BaseModel):
    """Прогон обучения."""

    model_config = ConfigDict(extra="ignore")

    version: str
    kind: ModelKind
    started_at: datetime
    finished_at: datetime | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    status: str = "running"
    notes: str = ""


class RebalanceAction(BaseModel):
    """Действие ребалансировки."""

    model_config = ConfigDict(extra="ignore")

    internal_id: str
    side: Literal["buy", "sell", "hold"]
    amount: Decimal
    weight_before: float
    weight_after: float
    reason: str


class RebalancePlan(BaseModel):
    """План ребалансировки."""

    model_config = ConfigDict(extra="ignore")

    strategy: str
    drift_threshold: float
    max_drift_observed: float
    actions: list[RebalanceAction]
    expected_return: float
    estimated_cost: float
    created_at: datetime


class Recommendation(BaseModel):
    """Рекомендация к покупке."""

    model_config = ConfigDict(extra="ignore")

    internal_id: str
    name: str
    decision: Decision
    confidence: float
    score: float
    predicted_return_pct: float | None
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    rank: int


class PortfolioPosition(BaseModel):
    """Позиция в портфеле пользователя."""

    model_config = ConfigDict(extra="ignore")

    user_id: int
    internal_id: str
    amount: Decimal
    opened_at: datetime
    current_price: float | None = None
    current_yield: float | None = None
