"""Users, subscriptions, billing events, preferences and alert models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scraper.orm._base import Base


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
    subscription_tier: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="free"
    )
    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Payment channel that established the current paid window: "stars" | "yookassa" | None.
    # A refund only revokes access when it matches the channel that actually paid.
    payment_channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.true())
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.false())
    referred_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    # Short shareable referral code (web referral program). Generated at
    # registration; unique across all users.
    referral_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # email/google_id/telegram_id are already UNIQUE (see column defs);
        # the unique constraint doubles as the lookup index, so no extra
        # non-unique indexes are needed on those columns.
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
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=func.false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # user_id is already UNIQUE (one subscription row per user) — the
        # unique constraint is the lookup index; keep the other useful ones.
        Index("ix_subscriptions_yookassa_payment", "yookassa_payment_id"),
        Index("ix_subscriptions_plan", "plan"),
    )


class BillingPaymentEventORM(Base):
    """Registry of already-processed billing notifications.

    YooKassa retries webhook deliveries without a message id, so the same
    ``payment.succeeded`` / ``payment.canceled`` / ``refund.succeeded`` can
    arrive multiple times (even after a newer payment superseded the
    subscription's current id). A row here means the notification was already
    acted on; re-deliveries are skipped (see api/billing/service.py).
    """

    __tablename__ = "billing_payment_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    payment_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_alert_rules_user", "user_id"),
        Index("ix_alert_rules_active", "active"),
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
