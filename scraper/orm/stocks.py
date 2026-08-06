"""Equity models: stocks and daily stock history."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
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
from sqlalchemy.orm import Mapped, mapped_column

from scraper.orm._base import Base


class StockORM(Base):
    """Акция с MOEX."""

    __tablename__ = "stocks"

    internal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    secid: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    isin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    board: Mapped[str] = mapped_column(String(8), nullable=False, server_default="TQBR")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, server_default="RUB")
    lot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prev_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    open_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_traded: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    market_capitalization: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    pe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    pbr_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    dividend_yield: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    earnings_per_share: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unknown")
    raw: Mapped[dict | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_stocks_secid", "secid"),
        Index("ix_stocks_board", "board"),
        Index("ix_stocks_status", "status"),
        Index("ix_stocks_sector", "sector"),
        Index("ix_stocks_price", "price"),
    )


class StockHistoryORM(Base):
    """История торгов акцией (дневные свечи)."""

    __tablename__ = "stock_history"

    internal_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("stocks.internal_id", ondelete="CASCADE"),
        primary_key=True,
    )
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    high_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    low_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_traded: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    weighted_avg_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unknown")

    __table_args__ = (Index("ix_stock_history_id_date", "internal_id", "date"),)
