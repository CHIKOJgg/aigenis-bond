"""add yookassa_payment_id to subscriptions

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-07-10 16:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a1b2c3d4e5"
down_revision: str | None = "e5f6a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column("yookassa_payment_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_subscriptions_yookassa_payment",
        "subscriptions",
        ["yookassa_payment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscriptions_yookassa_payment")
    op.drop_column("subscriptions", "yookassa_payment_id")
