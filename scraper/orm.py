from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BondORM(Base):
    __tablename__ = "bonds"

    internal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    isin: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    issuer_logo: Mapped[str | None] = mapped_column(String(512), nullable=True)

    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    nominal: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    coupon_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    coupon_frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)

    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    yield_to_maturity: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    amortization: Mapped[str | None] = mapped_column(String(16), nullable=True)
    offer_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    registration_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issue_volume: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    income_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    in_stock: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    guarantor: Mapped[str | None] = mapped_column(String(256), nullable=True)
    maturity_term_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    coupon_description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    coupon_schedule: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    indexation_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    exchange_rate_on_start: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    term_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unknown")
    is_government: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.false()
    )
    raw: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_bonds_currency", "currency"),
        Index("ix_bonds_status", "status"),
        Index("ix_bonds_yield_desc", "yield_to_maturity"),
        Index("ix_bonds_maturity", "maturity_date"),
    )


class BondHistoryORM(Base):
    __tablename__ = "bond_history"

    internal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bonds.internal_id", ondelete="CASCADE"),
        primary_key=True,
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)

    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    yield_: Mapped[Decimal | None] = mapped_column("yield", Numeric(10, 4), nullable=True)
    coupon: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unknown")

    __table_args__ = (Index("ix_history_id_date", "internal_id", "date"),)


class BondDailyAccrualORM(Base):
    __tablename__ = "bond_daily_accruals"

    internal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bonds.internal_id", ondelete="CASCADE"),
        primary_key=True,
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)

    accrued: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    total_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    __table_args__ = (Index("ix_accrual_id_date", "internal_id", "date"),)


class ParseErrorORM(Base):
    __tablename__ = "parse_errors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    internal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(2048), nullable=False)
    payload: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_errors_internal_id", "internal_id"),
        Index("ix_errors_created_at", "created_at"),
    )


class BondScoreORM(Base):
    __tablename__ = "bond_scores"

    internal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("bonds.internal_id", ondelete="CASCADE"),
        primary_key=True,
    )
    score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    tier: Mapped[str | None] = mapped_column(String(4), nullable=True)
    breakdown: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AlertORM(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(String(2048), nullable=False)
    internal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    dedup_key: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_alerts_kind", "kind"),
        Index("ix_alerts_created_at", "created_at"),
        Index("ix_alerts_dedup_key", "dedup_key"),
    )


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    google_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, unique=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="user")
    subscription_tier: Mapped[str] = mapped_column(String(32), nullable=False, server_default="free")
    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.true())
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_google_id", "google_id"),
        Index("ix_users_telegram_id", "telegram_id"),
        Index("ix_users_role", "role"),
        Index("ix_users_subscription_tier", "subscription_tier"),
    )


class SubscriptionORM(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    # YooKassa payment identifier
    yookassa_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, server_default="free")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="incomplete")
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_subscriptions_user_id", "user_id"),
        Index("ix_subscriptions_yookassa_payment", "yookassa_payment_id"),
        Index("ix_subscriptions_plan", "plan"),
    )


class UserPreferencesORM(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    initial_capital: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default="10000"
    )
    monthly_contribution: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default="500"
    )
    usd_byn_forecast: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, server_default="3.30"
    )
    share_usd: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.5")
    share_byn: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="0.3")
    share_metals: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, server_default="0.2"
    )
    share_eur: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, server_default="0")
    strategy: Mapped[str] = mapped_column(String(32), nullable=False, server_default="Balanced")
    watchlist: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FxRateORM(Base):
    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pair: Mapped[str] = mapped_column(String(8), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_fx_pair_date", "pair", "observed_at"),)


class MetalPriceORM(Base):
    __tablename__ = "metal_prices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metal: Mapped[str] = mapped_column(String(8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(16, 6), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_metal_observed", "metal", "observed_at"),)


class ModelVersionORM(Base):
    __tablename__ = "model_versions"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    train_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(512), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    __table_args__ = (Index("ix_model_versions_kind", "kind"),)


class TrainingRunORM(Base):
    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="running")
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    __table_args__ = (
        Index("ix_training_runs_started", "started_at"),
        Index("ix_training_runs_version", "version"),
    )


class PredictionORM(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    internal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    asof_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_ytm: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    predicted_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    predicted_volatility: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    feature_importance: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    explanation: Mapped[list | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_predictions_internal_id", "internal_id"),
        Index("ix_predictions_asof", "asof_date"),
        Index("ix_predictions_decision", "decision"),
    )


class PortfolioPositionORM(Base):
    __tablename__ = "portfolio_positions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    internal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    current_yield: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    __table_args__ = (
        Index("ix_positions_user_id", "user_id"),
        UniqueConstraint("user_id", "internal_id", name="uq_position_user_bond"),
    )


class RebalanceHistoryORM(Base):
    __tablename__ = "rebalance_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    drift_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    max_drift_observed: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    expected_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    actions: Mapped[list] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.false())

    __table_args__ = (
        Index("ix_rebalance_user", "user_id"),
        Index("ix_rebalance_created", "created_at"),
    )


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
    )


class AlertRuleORM(Base):
    """Пользовательские правила алертов (цена / доходность пробила порог)."""

    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    internal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    metric: Mapped[str] = mapped_column(String(16), nullable=False)  # price | ytm
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # above | below
    threshold: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.true())
    last_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_alert_rules_user", "user_id"),
        Index("ix_alert_rules_active", "active"),
    )


class CompanyORM(Base):
    """Профиль эмитента (компании): описание, сектор, почему важна.

    Ключ ``issuer`` совпадает со строкой ``bonds.issuer`` и связывает профиль
    с выпусками облигаций. Заполняется скриптом-сидом + вручную.
    """

    __tablename__ = "companies"

    issuer: Mapped[str] = mapped_column(String(512), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    why_important: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_companies_sector", "sector"),
        Index("ix_companies_name", "name"),
    )


class AlertEventORM(Base):
    """Срабатывания пользовательских алертов (лента уведомлений)."""

    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rule_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    internal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    metric: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    delivered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_alert_events_user", "user_id"),
        Index("ix_alert_events_created", "created_at"),
    )
