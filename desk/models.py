"""Модели V4: Mini Fixed Income Desk."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CurveTenor = Literal["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
StressKind = Literal["parallel", "steepener", "flattener", "inversion", "credit_shock", "fx_shock"]
RVSide = Literal["buy", "sell", "hold"]


class CurvePoint(BaseModel):
    """Точка кривой доходности."""

    model_config = ConfigDict(extra="ignore")

    tenor: CurveTenor
    years: float
    rate_pct: float


class YieldCurve(BaseModel):
    """Снимок кривой доходности."""

    model_config = ConfigDict(extra="ignore")

    currency: str
    observed_at: datetime
    points: list[CurvePoint]

    def short_rate(self) -> float:
        if not self.points:
            return 0.0
        return min((p.rate_pct for p in self.points), default=0.0)

    def long_rate(self) -> float:
        if not self.points:
            return 0.0
        return max((p.rate_pct for p in self.points), default=0.0)

    def slope(self) -> float:
        return self.long_rate() - self.short_rate()


class NelsonSiegelParams(BaseModel):
    """Параметры Nelson-Siegel."""

    beta0: float
    beta1: float
    beta2: float
    tau: float = 1.5


class RVSignal(BaseModel):
    """Relative Value сигнал: rich/cheap относительно peer-группы."""

    model_config = ConfigDict(extra="ignore")

    internal_id: str
    peer_currency: str
    peer_set: list[str] = Field(default_factory=list)
    z_score: float
    spread_pct: float
    fair_spread_pct: float
    side: RVSide
    rationale: str
    asof_date: date


class CarryTrade(BaseModel):
    """Carry-сделка: длинная позиция в облигации, фандинг по short-rate."""

    model_config = ConfigDict(extra="ignore")

    internal_id: str
    notional: Decimal
    coupon_pct: float
    funding_rate_pct: float
    rolldown_bps: float
    expected_pnl_pct: float
    breakeven_bps: float
    horizon_days: int
    asof_date: date


class RepoDeal(BaseModel):
    """Сделка РЕПО (простое моделирование)."""

    model_config = ConfigDict(extra="ignore")

    internal_id: str
    notional: Decimal
    haircut_pct: float
    repo_rate_pct: float
    tenor_days: int
    cash_lent: Decimal
    collateral_value: Decimal
    accrued_interest: Decimal
    asof_date: date


class DurationReport(BaseModel):
    """Отчёт по дюрации/выпуклости портфеля."""

    model_config = ConfigDict(extra="ignore")

    internal_id: str | None = None
    modified_duration: float
    macaulay_duration: float
    convexity: float
    dv01: float
    accrued_interest: float = 0.0
    key_rate_durations: dict[str, float] = Field(default_factory=dict)
    asof_date: date


class StressScenario(BaseModel):
    """Сценарий стресс-тестирования."""

    model_config = ConfigDict(extra="ignore")

    kind: StressKind
    name: str
    description: str
    rate_shocks: dict[str, float] = Field(default_factory=dict)
    fx_shock_pct: float = 0.0
    credit_spread_shock_bps: float = 0.0


class StressResult(BaseModel):
    """Результат прогона стресс-сценария."""

    model_config = ConfigDict(extra="ignore")

    scenario: StressScenario
    portfolio_value: Decimal
    stressed_value: Decimal
    pnl: Decimal
    pnl_pct: float
    by_position: dict[str, Decimal] = Field(default_factory=dict)
    by_tenor: dict[str, Decimal] = Field(default_factory=dict)
    asof_date: date
