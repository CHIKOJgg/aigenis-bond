"""add issuer_logo to bonds

Revision ID: 0009_issuer_logo
Revises: 0008_alert_rules
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_issuer_logo"
down_revision = "0008_alert_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bonds", sa.Column("issuer_logo", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("bonds", "issuer_logo")
