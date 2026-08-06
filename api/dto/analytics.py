"""Response DTOs for the analytics API.

Pure pydantic models — no ORM imports here. Builders convert domain objects
(``scraper.models.Bond``, ``scoring.models.BondScore``, desk dataclasses) into
wire-ready DTOs so routes and services stay decoupled from ORM entities.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from scraper.models import Bond


class BondFacts(BaseModel):
    internal_id: str
    name: str | None = None
    currency: str | None = None
    issuer: str | None = None
    yield_to_maturity: float | None = None
    coupon_rate: float | None = None
    price: float | None = None
    nominal: float | None = None
    maturity_date: str | None = None
    status: str | None = None


def bond_facts(bond: Bond) -> BondFacts:
    return BondFacts(
        internal_id=bond.internal_id,
        name=bond.name,
        currency=bond.currency,
        issuer=bond.issuer,
        yield_to_maturity=float(bond.yield_to_maturity) if bond.yield_to_maturity else None,
        coupon_rate=float(bond.coupon_rate) if bond.coupon_rate else None,
        price=float(bond.price) if bond.price else None,
        nominal=float(bond.nominal) if bond.nominal else None,
        maturity_date=bond.maturity_date.isoformat() if bond.maturity_date else None,
        status=bond.status,
    )


class TopBondRow(BaseModel):
    internal_id: str
    score: float
    tier: str | None = None


class CurrencyBondRow(BaseModel):
    internal_id: str
    name: str | None = None
    currency: str | None = None
    yield_to_maturity: float | None = None
    price: float | None = None
    issuer: str | None = None
    maturity_date: str | None = None
    status: str | None = None


class SubscribePlan(BaseModel):
    tier: str
    name: str
    stars: int
    duration_days: int
    blurb: str


class YookassaPlan(BaseModel):
    tier: str
    name: str
    price: str
    currency: str
    interval: str


class SubscribeInfo(BaseModel):
    provider: str
    yookassa_configured: bool
    yookassa_plans: list[YookassaPlan]
    bot_username: str | None = None
    deep_link: str | None = None
    plans: list[SubscribePlan]


class RvSignal(BaseModel):
    internal_id: str
    side: str | None = None
    z_score: float | None = None
    spread_pct: float | None = None


class MlPrediction(BaseModel):
    decision: str
    confidence: float | None = None
    predicted_ytm: float | None = None
    predicted_return_pct: float | None = None
    explanation: list[str] = []


class BondCard(BaseModel):
    bond: BondFacts
    score: float
    tier: str
    analysis: dict[str, Any] | None = None
    analysis_locked: bool = False
    upgrade_hint: str | None = None


class BondAnalysisPayload(BaseModel):
    bond: BondFacts
    analysis: dict[str, Any]
    relative_value: RvSignal | None = None
    ml_prediction: MlPrediction | None = None
    disclaimer: str


class CashflowPlan(BaseModel):
    bond: BondFacts
    amount_invested: float
    annual_income: float
    yield_on_cost: float
    total_coupons: float
    accrued_interest: float
    cashflows: list[dict[str, Any]]


class HistoryPoint(BaseModel):
    date: str
    price: float | None = None
    ytm: float | None = None


# --- Desk analytics ---


class DurationReport(BaseModel):
    title: str
    macaulay_duration: float
    modified_duration: float
    convexity: float
    dv01: float
    key_rate_durations: dict[str, float]


class CarryTrade(BaseModel):
    internal_id: str
    coupon_pct: float
    rolldown_bps: float
    expected_pnl_pct: float


class RepoDeal(BaseModel):
    internal_id: str
    collateral_value: float
    haircut_pct: float
    cash_lent: float
    repo_rate_pct: float
    tenor_days: int
    accrued_interest: float


class StressResult(BaseModel):
    scenario: str
    kind: str
    pnl_pct: float
    pnl: float


class CurvePoint(BaseModel):
    tenor: str
    years: float
    rate_pct: float


class CurveReport(BaseModel):
    currency: str
    slope: float
    beta0: float
    beta1: float
    beta2: float
    points: list[CurvePoint]


class DeskStatus(BaseModel):
    rv: list[dict[str, Any]]
    stress: list[dict[str, Any]]
    spreads: list[dict[str, Any]]
