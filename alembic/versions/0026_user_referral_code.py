"""
User-level referral codes for the web referral program.

Regular (non-partner) users never got a referral code: /api/v1/partner/referrals
returned ``referral_code=None`` unless the user owned a B2B partner key, which
made the web referral program unusable for ordinary users (the Telegram bot has
its own ``ref_<id>`` deep links). Every user now gets a short unique code at
registration so they can share a referral link.

Revision ID: 0026_user_referral_code
Revises: 0025_billing_payment_events
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0026_user_referral_code"
down_revision = "0025_billing_payment_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("referral_code", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_column("users", "referral_code")
