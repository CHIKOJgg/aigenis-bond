"""Merge subscription_expiry and yookassa_payment_id branches

Revision ID: 0007_merge_heads_2
Revises: b2c3d4e5f6a1, f6a1b2c3d4e5
Create Date: 2026-07-12 19:50:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_merge_heads_2"
down_revision: str | tuple[str, str] = (
    "b2c3d4e5f6a1",
    "f6a1b2c3d4e5",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
