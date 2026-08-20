"""add issuer_financials table

Persist issuer financials parsed from public reports (scoring/financials.py) so
the data-driven issuer credit signal can be stored and reused instead of being
re-derived on every rating call.

Revision ID: 0032_issuer_financials
Revises: 0031_bond_order_book
Create Date: 2026-08-20 13:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_issuer_financials"
down_revision: str = "0031_bond_order_book"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issuer_financials",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("period", sa.String(length=32), nullable=True),
        sa.Column("period_type", sa.String(length=16), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("revenue", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("net_income", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("ebitda", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("assets", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("equity", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("liabilities", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("current_assets", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column(
            "current_liabilities", sa.Numeric(precision=24, scale=4), nullable=True
        ),
        sa.Column("debt", sa.Numeric(precision=24, scale=4), nullable=True),
        sa.Column("source_url", sa.String(length=1024), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("credit_score", sa.Numeric(precision=6, scale=3), nullable=True),
        sa.Column("basis", sa.Text(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_issuer_financials_issuer", "issuer_financials", ["issuer"])
    op.create_index("ix_issuer_financials_period", "issuer_financials", ["period"])


def downgrade() -> None:
    op.drop_index("ix_issuer_financials_period", table_name="issuer_financials")
    op.drop_index("ix_issuer_financials_issuer", table_name="issuer_financials")
    op.drop_table("issuer_financials")
