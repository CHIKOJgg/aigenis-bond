"""partner API keys and webhooks

Revision ID: 0012_partner_api
Revises: 0011_is_government
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0012_partner_api"
down_revision = "0011_is_government"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("key_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("tier", sa.String(16), nullable=False, server_default="partner"),
        sa.Column("rate_limit", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_partner_api_keys_owner", "partner_api_keys", ["owner_user_id"])

    op.create_table(
        "partner_webhooks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "partner_key_id",
            sa.Integer(),
            sa.ForeignKey("partner_api_keys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("events", sa.JSON().with_variant(JSONB(), "postgresql"), nullable=False),
        sa.Column("secret", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_error", sa.String(512), nullable=True),
        sa.Column("last_delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_partner_webhooks_partner", "partner_webhooks", ["partner_key_id"])


def downgrade() -> None:
    op.drop_index("ix_partner_webhooks_partner", table_name="partner_webhooks")
    op.drop_table("partner_webhooks")
    op.drop_index("ix_partner_api_keys_owner", table_name="partner_api_keys")
    op.drop_table("partner_api_keys")
