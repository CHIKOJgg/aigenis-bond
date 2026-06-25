"""add registration_number, issue_volume, issue_number, income_method, in_stock, guarantor, maturity_term_text, coupon_description, coupon_schedule to bonds

Revision ID: 0005_bond_extra_fields
Revises: 0004_v4
Create Date: 2026-06-20 21:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_bond_extra_fields"
down_revision: str | None = "0004_v4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bonds", sa.Column("registration_number", sa.String(64), nullable=True))
    op.add_column("bonds", sa.Column("issue_volume", sa.Numeric(20, 6), nullable=True))
    op.add_column("bonds", sa.Column("issue_number", sa.Integer(), nullable=True))
    op.add_column("bonds", sa.Column("income_method", sa.String(16), nullable=True))
    op.add_column("bonds", sa.Column("in_stock", sa.Boolean(), nullable=True))
    op.add_column("bonds", sa.Column("guarantor", sa.String(256), nullable=True))
    op.add_column("bonds", sa.Column("maturity_term_text", sa.String(64), nullable=True))
    op.add_column("bonds", sa.Column("coupon_description", sa.String(256), nullable=True))
    op.add_column(
        "bonds",
        sa.Column(
            "coupon_schedule", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("bonds", "coupon_schedule")
    op.drop_column("bonds", "coupon_description")
    op.drop_column("bonds", "maturity_term_text")
    op.drop_column("bonds", "guarantor")
    op.drop_column("bonds", "in_stock")
    op.drop_column("bonds", "income_method")
    op.drop_column("bonds", "issue_number")
    op.drop_column("bonds", "issue_volume")
    op.drop_column("bonds", "registration_number")
