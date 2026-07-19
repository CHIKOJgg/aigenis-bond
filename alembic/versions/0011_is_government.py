"""add is_government flag to bonds

Revision ID: 0011_is_government
Revises: 0010_companies
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_is_government"
down_revision = "0010_companies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bonds",
        sa.Column(
            "is_government",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_bonds_is_government", "bonds", ["is_government"]
    )


def downgrade() -> None:
    op.drop_index("ix_bonds_is_government", table_name="bonds")
    op.drop_column("bonds", "is_government")
