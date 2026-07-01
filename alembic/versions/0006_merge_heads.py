"""Merge 0005_peer_set branch into main chain

Revision ID: 0006_merge_heads
Revises: 0006_bond_extra_fields_2, 0005_peer_set
Create Date: 2026-06-28 22:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_merge_heads"
down_revision: str | tuple[str, str] = (
    "0006_bond_extra_fields_2",
    "0005_peer_set",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
