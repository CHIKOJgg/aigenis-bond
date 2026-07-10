"""add subscription expiry and last charge id to users

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f0
Create Date: 2026-07-10 13:00:00.000000

Adds Telegram Stars subscription bookkeeping to ``users``:

* ``subscription_expires_at`` — when the current paid tier lapses back to free.
* ``last_charge_id`` — Telegram payment charge id used for idempotent
  ``successful_payment`` handling and refund matching.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a1"
down_revision: str | None = "a1b2c3d4e5f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("users", sa.Column("last_charge_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_charge_id")
    op.drop_column("users", "subscription_expires_at")
