"""Bond market models: bonds, history, daily accruals, scores, companies."""

from __future__ import annotations

import math
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
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates

from scraper.orm._base import Base


def _clamp_numeric(value: object, max_abs: float) -> object:
    """Drop physically impossible magnitudes so a bad feed value can never
    overflow a ``NUMERIC(p, s)`` column and abort the whole ingestion batch.

    Returns ``None`` for ``None``/non-finite/out-of-range values, otherwise the
    original value untouched.
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or abs(f) >= max_abs:
        return None
    return value


class BondORM(Base):
    __tablename__ = "bonds"

    internal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    isin: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    issuer_logo: Mapped[str | None] = mapped_column(String(512), nullable=True)

    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    nominal: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    coupon_rate: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    coupon_frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)

    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    yield_to_maturity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

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

    market: Mapped[str] = mapped_column(
        String(4), nullable=False, server_default="bcse", index=True
    )
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
        Index("ix_bonds_is_government", "is_government"),
    )

    @validates(
        "nominal",
        "price",
        "issue_volume",
        "exchange_rate_on_start",
        "coupon_rate",
        "yield_to_maturity",
    )
    def _validate_numeric(self, key: str, value: object) -> object:
        # NUMERIC(20, 6) columns overflow above ~1e14; NUMERIC(14, 4) above ~1e10.
        max_abs = 1e13 if key in {"nominal", "price", "issue_volume", "exchange_rate_on_start"} else 1e9
        return _clamp_numeric(value, max_abs)

    @validates("term_days", "quantity")
    def _validate_int(self, key: str, value: object) -> object:
        if value is None:
            return None
        try:
            iv = int(value)
        except (TypeError, ValueError):
            return None
        if iv < -2_000_000_000 or iv > 2_000_000_000:
            return None
        return iv


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

    __table_args__ = (Index("ix_scores_score_desc", score.desc()),)


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
