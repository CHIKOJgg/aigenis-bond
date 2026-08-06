"""Desk analytics models: curves, RV signals, carry trades, repo deals, stress runs, spread reports."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scraper.orm._base import Base


class CurvePointORM(Base):
    __tablename__ = "curve_points"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    tenor: Mapped[str] = mapped_column(String(8), nullable=False)
    years: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    rate_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ns_params: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    __table_args__ = (Index("ix_curve_currency_date", "currency", "observed_at"),)


class RVSignalORM(Base):
    __tablename__ = "rv_signals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    internal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    peer_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    z_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    spread_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    fair_spread_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    rationale: Mapped[str] = mapped_column(String(512), nullable=False)
    peer_set: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    asof_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_rv_internal_id", "internal_id"),
        Index("ix_rv_asof", "asof_date"),
        Index("ix_rv_side", "side"),
        Index("uq_rv_signal_day", "internal_id", "peer_currency", "asof_date", unique=True),
    )


class CarryTradeORM(Base):
    __tablename__ = "carry_trades"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    internal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    notional: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    coupon_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    funding_rate_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    rolldown_bps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    expected_pnl_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    breakeven_bps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    asof_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_carry_internal_id", "internal_id"),
        Index("ix_carry_asof", "asof_date"),
        Index("uq_carry_day", "internal_id", "asof_date", unique=True),
    )


class RepoDealORM(Base):
    __tablename__ = "repo_deals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    internal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    notional: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    haircut_pct: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    repo_rate_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    tenor_days: Mapped[int] = mapped_column(Integer, nullable=False)
    cash_lent: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    collateral_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    accrued_interest: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    asof_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_repo_internal_id", "internal_id"),)


class StressRunORM(Base):
    __tablename__ = "stress_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scenario_name: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    portfolio_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    stressed_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    pnl: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    pnl_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    by_position: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    by_tenor: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    asof_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_stress_name", "scenario_name"),
        Index("ix_stress_asof", "asof_date"),
        Index("uq_stress_day", "scenario_name", "asof_date", unique=True),
    )


class SpreadReportORM(Base):
    """Z/G-spread and model-vs-market pricing signal per bond."""

    __tablename__ = "spread_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    internal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    tenor_years: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    ytm_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    flat_yield_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    z_spread_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    g_spread_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    curve_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    model_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    mispricing_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    asof_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_spread_internal_id", "internal_id"),
        Index("ix_spread_asof", "asof_date"),
        Index("uq_spread_day", "internal_id", "asof_date", unique=True),
    )
