"""link partner lead to issued partner key

Revision ID: 0016_partner_lead_key
Revises: 0015_partner_lead
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016_partner_lead_key"
down_revision = "0015_partner_lead"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "partner_leads",
        sa.Column("partner_key_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_partner_leads_key", "partner_leads", ["partner_key_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_partner_leads_key", table_name="partner_leads")
    op.drop_column("partner_leads", "partner_key_id")
