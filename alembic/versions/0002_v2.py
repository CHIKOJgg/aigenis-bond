"""V2 schema: bond_scores, alerts, user_preferences, fx_rates, metal_prices

Revision ID: 0002_v2
Revises: 0001_init
Create Date: 2026-06-18 12:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_v2"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bond_scores",
        sa.Column(
            "internal_id",
            sa.String(length=64),
            sa.ForeignKey("bonds.internal_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("score", sa.Numeric(8, 2), nullable=False),
        sa.Column("tier", sa.String(length=4), nullable=True),
        sa.Column(
            "breakdown",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_scores_score_desc", "bond_scores", [sa.text("score DESC")])

    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("message", sa.String(length=2048), nullable=False),
        sa.Column("internal_id", sa.String(length=64), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("dedup_key", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_alerts_kind", "alerts", ["kind"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])
    op.create_index("ix_alerts_dedup_key", "alerts", ["dedup_key"], unique=False)

    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.BigInteger(), primary_key=True),
        sa.Column("initial_capital", sa.Numeric(20, 4), nullable=False, server_default="10000"),
        sa.Column(
            "monthly_contribution",
            sa.Numeric(20, 4),
            nullable=False,
            server_default="500",
        ),
        sa.Column(
            "usd_byn_forecast",
            sa.Numeric(12, 6),
            nullable=False,
            server_default="3.30",
        ),
        sa.Column("share_usd", sa.Numeric(5, 4), nullable=False, server_default="0.5"),
        sa.Column("share_byn", sa.Numeric(5, 4), nullable=False, server_default="0.3"),
        sa.Column("share_metals", sa.Numeric(5, 4), nullable=False, server_default="0.2"),
        sa.Column("share_eur", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("strategy", sa.String(length=32), nullable=False, server_default="Balanced"),
        sa.Column(
            "watchlist",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "fx_rates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("pair", sa.String(length=8), nullable=False),
        sa.Column("rate", sa.Numeric(16, 8), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_fx_pair_date", "fx_rates", ["pair", "observed_at"])

    op.create_table(
        "metal_prices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("metal", sa.String(length=8), nullable=False),
        sa.Column("price", sa.Numeric(16, 6), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_metal_observed", "metal_prices", ["metal", "observed_at"])


def downgrade() -> None:
    op.drop_index("ix_metal_observed", table_name="metal_prices")
    op.drop_table("metal_prices")

    op.drop_index("ix_fx_pair_date", table_name="fx_rates")
    op.drop_table("fx_rates")

    op.drop_table("user_preferences")

    op.drop_index("ix_alerts_dedup_key", table_name="alerts")
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_index("ix_alerts_kind", table_name="alerts")
    op.drop_table("alerts")

    op.drop_index("ix_scores_score_desc", table_name="bond_scores")
    op.drop_table("bond_scores")
