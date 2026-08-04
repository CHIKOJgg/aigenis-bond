"""add market column to bonds table

Revision ID: a1b2c3d4e5f6
Revises: f6a1b2c3d4e5
Create Date: 2026-08-04 17:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f6a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bonds",
        sa.Column("market", sa.String(length=4), nullable=False, server_default="bcse"),
    )
    op.create_index("ix_bonds_market", "bonds", ["market"])
    op.execute("UPDATE bonds SET market = 'moex' WHERE internal_id LIKE 'MOEX_%'")
    op.execute("UPDATE bonds SET market = 'moex' WHERE currency = 'RUB' AND internal_id NOT LIKE 'MOEX_%'")
    op.execute("UPDATE bonds SET market = 'bcse' WHERE currency = 'BYN' AND internal_id NOT LIKE 'MOEX_%'")


def downgrade() -> None:
    op.drop_index("ix_bonds_market")
    op.drop_column("bonds", "market")
