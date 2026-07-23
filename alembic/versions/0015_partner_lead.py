"""partner inbound lead table

Revision ID: 0015_partner_lead
Revises: 0014_partner_referral
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0015_partner_lead"
down_revision = "0014_partner_referral"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_leads",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(256), nullable=True),
        sa.Column("telegram", sa.String(64), nullable=True),
        sa.Column("company", sa.String(128), nullable=True),
        sa.Column("interest", sa.String(32), nullable=True),
        sa.Column("message", sa.String(2000), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("partner_leads")
