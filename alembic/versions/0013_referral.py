"""referral fields for users and partner keys

Revision ID: 0013_referral
Revises: 0012_partner_api
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013_referral"
down_revision = "0012_partner_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("referred_by", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_users_referred_by", "users", ["referred_by"])

    op.add_column(
        "partner_api_keys",
        sa.Column("referral_code", sa.String(32), nullable=True),
    )
    op.create_index(
        "ix_partner_api_keys_referral_code",
        "partner_api_keys",
        ["referral_code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_partner_api_keys_referral_code", table_name="partner_api_keys")
    op.drop_column("partner_api_keys", "referral_code")
    op.drop_index("ix_users_referred_by", table_name="users")
    op.drop_column("users", "referred_by")
