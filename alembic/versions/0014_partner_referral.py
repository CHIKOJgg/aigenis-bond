"""partner referral attribution table

Revision ID: 0014_partner_referral
Revises: 0013_referral
"""

from __future__ import annotations

import secrets

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0014_partner_referral"
down_revision = "0013_referral"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_referrals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("partner_key_id", sa.Integer(), nullable=True),
        sa.Column("referrer_user_id", sa.BigInteger(), nullable=True),
        sa.Column("referred_user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan", sa.String(32), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="BYN"),
        sa.Column("commission_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("payout_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_partner_referrals_partner", "partner_referrals", ["partner_key_id"])
    op.create_index("ix_partner_referrals_referrer", "partner_referrals", ["referrer_user_id"])
    op.create_index("ix_partner_referrals_referred", "partner_referrals", ["referred_user_id"])

    # Backfill a unique referral_code for any existing partner keys that lack one.
    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT id FROM partner_api_keys WHERE referral_code IS NULL")
    )
    for row in result.fetchall():
        code = secrets.token_urlsafe(8)[:10]
        # ensure uniqueness best-effort
        bind.execute(
            sa.text("UPDATE partner_api_keys SET referral_code = :c WHERE id = :i"),
            {"c": code, "i": row[0]},
        )


def downgrade() -> None:
    op.drop_index("ix_partner_referrals_referred", table_name="partner_referrals")
    op.drop_index("ix_partner_referrals_referrer", table_name="partner_referrals")
    op.drop_index("ix_partner_referrals_partner", table_name="partner_referrals")
    op.drop_table("partner_referrals")
