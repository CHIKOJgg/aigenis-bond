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
    "Metals++",
]

ScenarioName = Literal["Bull USD", "Neutral", "Bull BYN", "Stress"]


class ScoreBreakdown(BaseModel):
    """Раскладка Reward/Risk Score v4."""

    model_config = ConfigDict(extra="ignore")

    yield_component: float = 0.0
    currency_component: float = 0.0
    duration_component: float = 0.0
    liquidity_component: float = 0.0
    metal_component: float = 0.0
    credit_risk_component: float = 0.0
    inflation_component: float = 0.0
    coupon_component: float = 0.0
    volatility_component: float = 0.0
    historical_volatility_component: float = 0.0
    peer_relative_component: float = 0.0
    reward_subtotal: float = 0.0
    risk_subtotal: float = 0.0
    efficiency_ratio: float = 0.0

    def total(self) -> float:
        """Сумма 11 компонентов (без reward/risk/efficiency мета-полей)."""
        return float(
            sum(
                getattr(self, f)
                for f in (
                    "yield_component",
                    "currency_component",
                    "duration_component",
                    "liquidity_component",
                    "metal_component",
                    "credit_risk_component",
                    "inflation_component",
                    "coupon_component",
                    "volatility_component",
                    "historical_volatility_component",
                    "peer_relative_component",
                )
            )
        )


class BondScore(BaseModel):
    """Reward/Risk Score v4 для конкретной облигации."""

    model_config = ConfigDict(extra="ignore")

    internal_id: str
    score: float
    risk_adjusted_score: float = 0.0
    breakdown: ScoreBreakdown
    computed_at: datetime

    @property
    def tier(self) -> str:
        if self.score >= 85:
            return "S"
        if self.score >= 75:
            return "A"
        if self.score >= 60:
            return "B"
        if self.score >= 45:
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
    calmar: float = 0.0
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
    # Monte Carlo percentile distribution (p5/p25/p50/p75/p95) and the
    # expected shortfall of the worst 5% of outcomes, when simulated.
    mc_percentiles: dict[str, Decimal] = Field(default_factory=dict)
    cvar_95: Decimal | None = None


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
