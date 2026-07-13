"""add alert rules and alert events

Revision ID: 0008_alert_rules
Revises: 0007_merge_heads_2
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_alert_rules"
down_revision = "0007_merge_heads_2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("internal_id", sa.String(length=64), nullable=False),
        sa.Column("metric", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=20, scale=6), nullable=False),
        sa.Column("note", sa.String(length=256), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rules_user", "alert_rules", ["user_id"])
    op.create_index("ix_alert_rules_active", "alert_rules", ["active"])

    op.create_table(
        "alert_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=True),
        sa.Column("internal_id", sa.String(length=64), nullable=False),
        sa.Column("metric", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("value", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("delivered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_events_user", "alert_events", ["user_id"])
    op.create_index("ix_alert_events_created", "alert_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_alert_events_created", table_name="alert_events")
    op.drop_index("ix_alert_events_user", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index("ix_alert_rules_active", table_name="alert_rules")
    op.drop_index("ix_alert_rules_user", table_name="alert_rules")
    op.drop_table("alert_rules")
