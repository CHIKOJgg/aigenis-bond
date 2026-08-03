"""
Registry of processed billing payment notifications (webhook replay guard).

YooKassa retries webhook deliveries; the previous idempotency guard only
compared against the subscription's *current* payment id, so a redelivered
``payment.succeeded`` for an older payment (after a newer purchase) would
extend the subscription again for free. Every processed notification is
recorded here and re-deliveries are skipped.

Revision ID: 0025_billing_payment_events
Revises: 0024_alert_pk_identity
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0025_billing_payment_events"
down_revision = "0024_alert_pk_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_payment_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("payment_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_id", name="uq_billing_events_payment_id"),
    )
    op.create_index("ix_billing_events_user_id", "billing_payment_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_billing_events_user_id", table_name="billing_payment_events")
    op.drop_table("billing_payment_events")
