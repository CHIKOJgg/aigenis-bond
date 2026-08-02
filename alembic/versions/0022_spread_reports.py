"""
Spread reports (Z-spread / G-spread / model-vs-market pricing signal).

Revision ID: 0022_spread_reports
Revises: 0021_stock_tables
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0022_spread_reports"
down_revision = "0021_stock_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spread_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("internal_id", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("tenor_years", sa.Numeric(10, 6), nullable=True),
        sa.Column("ytm_pct", sa.Numeric(10, 6), nullable=True),
        sa.Column("flat_yield_pct", sa.Numeric(10, 6), nullable=True),
        sa.Column("z_spread_pct", sa.Numeric(10, 6), nullable=True),
        sa.Column("g_spread_pct", sa.Numeric(10, 6), nullable=True),
        sa.Column("curve_rate_pct", sa.Numeric(10, 6), nullable=True),
        sa.Column("model_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("market_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("mispricing_pct", sa.Numeric(10, 6), nullable=True),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("asof_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_spread_internal_id", "spread_reports", ["internal_id"], unique=False
    )
    op.create_index("ix_spread_asof", "spread_reports", ["asof_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_spread_asof", table_name="spread_reports")
    op.drop_index("ix_spread_internal_id", table_name="spread_reports")
    op.drop_table("spread_reports")
