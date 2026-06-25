"""Модели для scoring, portfolio, мониторинга, сценариев."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Currency = Literal["USD", "BYN", "EUR", "XAU", "XAG", "XPT"]

StrategyName = Literal[
    "Conservative",
    "Balanced",
    "Aggressive",
    "Carry Trade",
    "Dollarization",
    "Maximum Reward/Risk",
]

ScenarioName = Literal["Bull USD", "Neutral", "Bull BYN", "Stress"]


class ScoreBreakdown(BaseModel):
    """Раскладка Reward/Risk Score."""

    model_config = ConfigDict(extra="ignore")

    yield_component: float = 0.0
    currency_component: float = 0.0
    duration_component: float = 0.0
    liquidity_component: float = 0.0
    metal_component: float = 0.0
    credit_risk_component: float = 0.0
    inflation_component: float = 0.0

    def total(self) -> float:
        return float(sum(self.model_dump().values()))


class BondScore(BaseModel):
    """Reward/Risk Score для конкретной облигации."""

    model_config = ConfigDict(extra="ignore")

    internal_id: str
    score: float
    breakdown: ScoreBreakdown
    computed_at: datetime

    @property
    def tier(self) -> str:
        if self.score >= 90:
            return "S"
        if self.score >= 80:
            return "A"
        if self.score >= 70:
            return "B"
        if self.score >= 60:
            return "C"
        return "D"


class UserPreferences(BaseModel):
    """Пользовательские настройки портфеля."""

    model_config = ConfigDict(extra="ignore")

    user_id: int
    initial_capital: Decimal = Decimal("10000")
    monthly_contribution: Decimal = Decimal("500")
    usd_byn_forecast: Decimal = Decimal("3.30")

    share_usd: float = Field(0.5, ge=0.0, le=1.0)
    share_byn: float = Field(0.3, ge=0.0, le=1.0)
    share_metals: float = Field(0.2, ge=0.0, le=1.0)
    share_eur: float = Field(0.0, ge=0.0, le=1.0)

    strategy: StrategyName = "Balanced"
    watchlist: list[str] = Field(default_factory=list)


class PortfolioAllocation(BaseModel):
    """Распределение капитала по облигациям/металлам."""

    model_config = ConfigDict(extra="ignore")

    items: dict[str, Decimal]
    expected_return: float
    volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    var_95: float
    strategy: StrategyName


class ForecastResult(BaseModel):
    """Прогноз роста капитала."""

    model_config = ConfigDict(extra="ignore")

    horizon_years: int
    initial_capital: Decimal
    monthly_contribution: Decimal
    expected_capital: Decimal
    pessimistic_capital: Decimal
    optimistic_capital: Decimal
    expected_return: float
    assumptions: dict[str, str] = Field(default_factory=dict)


class ScenarioResult(BaseModel):
    """Результат сценария USD/BYN."""

    model_config = ConfigDict(extra="ignore")

    scenario: ScenarioName
    usd_byn_start: Decimal
    usd_byn_end: Decimal
    fx_change_pct: float
    portfolio_value_change_pct: float
    worst_position: str | None = None
    notes: list[str] = Field(default_factory=list)


AlertKind = Literal[
    "new_bond",
    "yield_drop",
    "yield_rise",
    "coupon_change",
    "price_change",
    "offer",
    "matured",
    "high_score",
    "fx_usd_byn",
    "metal_xau",
    "metal_xag",
    "metal_xpt",
]


class Alert(BaseModel):
    """Уведомление для пользователя."""

    model_config = ConfigDict(extra="ignore")

    kind: str
    title: str
    message: str
    internal_id: str | None = None
    payload: dict = Field(default_factory=dict)
    created_at: datetime
