"""Add peer_set column to rv_signals

Revision ID: 0005_peer_set
Revises: 0004_v4
Create Date: 2026-06-18 21:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_peer_set"
down_revision: str | None = "0004_v4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rv_signals",
        sa.Column(
            "peer_set",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("rv_signals", "peer_set")
