"""
Fix numeric precision for coupon_rate and yield_to_maturity.

Revision ID: 0018_fix_numeric_precision
Revises: abc123456789
Branch labels: None
depends_on: None

Uses batch_alter_table so the migration also works on SQLite, where a plain
ALTER COLUMN TYPE is unsupported (batch mode is a pass-through on Postgres).
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "0018_fix_numeric_precision"
down_revision = "abc123456789"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bonds") as batch_op:
        batch_op.alter_column(
            "coupon_rate",
            type_=sa.Numeric(14, 4),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "yield_to_maturity",
            type_=sa.Numeric(14, 4),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("bonds") as batch_op:
        batch_op.alter_column(
            "coupon_rate",
            type_=sa.Numeric(10, 4),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "yield_to_maturity",
            type_=sa.Numeric(10, 4),
            existing_nullable=True,
        )
