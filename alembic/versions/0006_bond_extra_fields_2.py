"""add quantity, indexation_currency, exchange_rate_on_start, term_days to bonds + bond_daily_accruals table

Revision ID: 0006_bond_extra_fields_2
Revises: 0005_bond_extra_fields
Create Date: 2026-06-20 21:30:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_bond_extra_fields_2"
down_revision: str | None = "0005_bond_extra_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bonds", sa.Column("quantity", sa.Integer(), nullable=True))
    op.add_column("bonds", sa.Column("indexation_currency", sa.String(8), nullable=True))
    op.add_column("bonds", sa.Column("exchange_rate_on_start", sa.Numeric(20, 6), nullable=True))
    op.add_column("bonds", sa.Column("term_days", sa.Integer(), nullable=True))

    op.create_table(
        "bond_daily_accruals",
        sa.Column(
            "internal_id",
            sa.String(64),
            sa.ForeignKey("bonds.internal_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("accrued", sa.Numeric(20, 6), nullable=True),
        sa.Column("total_value", sa.Numeric(20, 6), nullable=True),
    )
    op.create_index("ix_accrual_id_date", "bond_daily_accruals", ["internal_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_accrual_id_date", table_name="bond_daily_accruals")
    op.drop_table("bond_daily_accruals")

    op.drop_column("bonds", "term_days")
    op.drop_column("bonds", "exchange_rate_on_start")
    op.drop_column("bonds", "indexation_currency")
    op.drop_column("bonds", "quantity")
