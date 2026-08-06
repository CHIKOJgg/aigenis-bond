"""Personal portfolio models: positions, rebalance history, transactions, P&L, backtests."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from scraper.orm._base import Base


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


class TransactionORM(Base):
    """Portfolio transaction log — every buy/sell recorded."""

    __tablename__ = "portfolio_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    internal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # "buy" | "sell"
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        Index("ix_tx_user_id", "user_id"),
        Index("ix_tx_executed", "executed_at"),
    )


class PnLSnapshotORM(Base):
    """Daily P&L snapshots per user — for equity curve charts."""

    __tablename__ = "portfolio_pnl_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    invested: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default="0"
    )
    unrealized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default="0"
    )
    coupon_income: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, server_default="0"
    )
    daily_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    __table_args__ = (
        # The unique constraint on (user_id, date) already serves as the
        # lookup index for the per-user daily query — no duplicate needed.
        UniqueConstraint("user_id", "date", name="uq_pnl_user_date"),
    )


class BacktestORM(Base):
    """Saved backtest results for a user."""

    __tablename__ = "portfolio_backtests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    final_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    total_return_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    annual_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    max_drawdown_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    equity_curve: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    positions_history: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_backtest_user_id", "user_id"),)
