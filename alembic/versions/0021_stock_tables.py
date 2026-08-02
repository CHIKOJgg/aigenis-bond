"""
Stocks and stock history tables (MOEX equities API).

The ORM defined these tables but no migration ever created them, so
/api/v1/stocks* endpoints 500 on a fresh database.

Revision ID: 0021_stock_tables
Revises: 0020_document_analysis
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021_stock_tables"
down_revision = "0020_document_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stocks",
        sa.Column("internal_id", sa.String(length=64), nullable=False),
        sa.Column("secid", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("isin", sa.String(length=32), nullable=True),
        sa.Column("issuer", sa.String(length=512), nullable=True),
        sa.Column("board", sa.String(length=8), server_default="TQBR", nullable=False),
        sa.Column("currency", sa.String(length=8), server_default="RUB", nullable=False),
        sa.Column("lot_size", sa.Integer(), nullable=True),
        sa.Column("prev_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("price", sa.Numeric(20, 6), nullable=True),
        sa.Column("open_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("high_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("low_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("close_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("value_traded", sa.Numeric(20, 6), nullable=True),
        sa.Column("market_capitalization", sa.Numeric(24, 6), nullable=True),
        sa.Column("pe_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("pbr_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("dividend_yield", sa.Numeric(10, 4), nullable=True),
        sa.Column("earnings_per_share", sa.Numeric(20, 6), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="unknown", nullable=False),
        sa.Column(
            "raw",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("internal_id"),
    )
    op.create_index("ix_stocks_secid", "stocks", ["secid"], unique=False)
    op.create_index("ix_stocks_board", "stocks", ["board"], unique=False)
    op.create_index("ix_stocks_status", "stocks", ["status"], unique=False)
    op.create_index("ix_stocks_sector", "stocks", ["sector"], unique=False)
    op.create_index("ix_stocks_price", "stocks", ["price"], unique=False)

    op.create_table(
        "stock_history",
        sa.Column("internal_id", sa.String(length=64), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("high_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("low_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("close_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("value_traded", sa.Numeric(20, 6), nullable=True),
        sa.Column("weighted_avg_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="unknown", nullable=False),
        sa.ForeignKeyConstraint(
            ["internal_id"], ["stocks.internal_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("internal_id", "date"),
    )
    op.create_index(
        "ix_stock_history_id_date", "stock_history", ["internal_id", "date"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_stock_history_id_date", table_name="stock_history")
    op.drop_table("stock_history")
    op.drop_index("ix_stocks_price", table_name="stocks")
    op.drop_index("ix_stocks_sector", table_name="stocks")
    op.drop_index("ix_stocks_status", table_name="stocks")
    op.drop_index("ix_stocks_board", table_name="stocks")
    op.drop_index("ix_stocks_secid", table_name="stocks")
    op.drop_table("stocks")
