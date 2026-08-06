"""Partner / B2B models: API keys, referrals, leads, webhooks."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scraper.orm._base import Base


class PartnerKeyORM(Base):
    """API-ключи для партнёрской интеграции (B2B / вебхуки).

    В БД хранится только хэш ключа (bcrypt) плюс быстрый SHA-256
    отпечаток ``key_fp`` для lookup без перебора всех ключей
    (bcrypt-verify по одному ключу не даёт возможность CPU-DoS).
    Сам секрет возвращается единожды при создании и больше нигде не логируется.
    """

    __tablename__ = "partner_api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    # unique=True already creates the lookup index for key_fp — no separate
    # index=True (that would duplicate it).
    key_fp: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, server_default="partner")
    rate_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default="120")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.true())
    referral_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    branding: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True, server_default="{}"
    )

    __table_args__ = (Index("ix_partner_api_keys_owner", "owner_user_id"),)


class PartnerReferralORM(Base):
    """Attribution of a converted subscription to a partner/referrer.

    When a user pays via a partner's referral code (or a user's ``referral_code``
    deep link), we record the conversion here so the partner can be paid out
    (manually or via Stars). One row per successfully activated subscription.
    """

    __tablename__ = "partner_referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partner_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    referrer_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    referred_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="BYN")
    commission_pct: Mapped[float] = mapped_column(nullable=False, default=0.0)
    payout_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PartnerLeadORM(Base):
    """Inbound B2B partnership / white-label / affiliate requests.

    Captured from the public ``/partners`` landing page (see ``api/seo.py``).
    A lead is recorded before a partner key exists, so the team can qualify and
    convert it manually. An alert is pushed to Telegram on creation.
    """

    __tablename__ = "partner_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    telegram: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interest: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="new")
    partner_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WebhookORM(Base):
    """Подписки на события партнёра (webhook-доставка).

    ``events`` — список типов событий (bond.updated, alert.triggered, …).
    ``secret`` используется для HMAC-SHA256 подписи тела запроса.
    """

    __tablename__ = "partner_webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    partner_key_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("partner_api_keys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    events: Mapped[list] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=list
    )
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=func.true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_partner_webhooks_partner", "partner_key_id"),)
