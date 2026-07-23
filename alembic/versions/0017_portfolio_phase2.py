"""Add portfolio transactions, P&L snapshots, and backtests.

Revision ID: 0017_portfolio_phase2
Revises: 0016_partner_lead_key
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0017_portfolio_phase2"
down_revision = "0016_partner_lead_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Portfolio transactions log
    op.create_table(
        "portfolio_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("internal_id", sa.String(64), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("price", sa.Numeric(20, 6), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("note", sa.String(512), nullable=True),
    )
    op.create_index("ix_tx_user_id", "portfolio_transactions", ["user_id"])
    op.create_index("ix_tx_executed", "portfolio_transactions", ["executed_at"])

    # P&L snapshots
    op.create_table(
        "portfolio_pnl_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("total_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("invested", sa.Numeric(20, 4), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(20, 4), nullable=False, server_default="0"),
        sa.Column("unrealized_pnl", sa.Numeric(20, 4), nullable=False, server_default="0"),
        sa.Column("coupon_income", sa.Numeric(20, 4), nullable=False, server_default="0"),
        sa.Column("daily_return_pct", sa.Numeric(10, 4), nullable=True),
        sa.UniqueConstraint("user_id", "date", name="uq_pnl_user_date"),
    )
    op.create_index("ix_pnl_user_date", "portfolio_pnl_snapshots", ["user_id", "date"])

    # Backtest results
    op.create_table(
        "portfolio_backtests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("initial_capital", sa.Numeric(20, 4), nullable=False),
        sa.Column("final_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("total_return_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("annual_return_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("max_drawdown_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("equity_curve", sa.JSON(), nullable=False),
        sa.Column("positions_history", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_backtest_user_id", "portfolio_backtests", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_backtest_user_id", table_name="portfolio_backtests")
    op.drop_table("portfolio_backtests")
    op.drop_index("ix_pnl_user_date", table_name="portfolio_pnl_snapshots")
    op.drop_table("portfolio_pnl_snapshots")
    op.drop_index("ix_tx_executed", table_name="portfolio_transactions")
    op.drop_index("ix_tx_user_id", table_name="portfolio_transactions")
    op.drop_table("portfolio_transactions")
