"""add trial_end to users for free trial support

Revision ID: d4e5f6a1b2c3
Revises: c845972200a0
Create Date: 2026-07-10 14:00:00.000000

Adds ``trial_end`` column to ``users`` so new registrations can enjoy a
time-limited free trial of Pro features without entering payment details.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a1b2c3"
down_revision: str | None = "c845972200a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "trial_end")
