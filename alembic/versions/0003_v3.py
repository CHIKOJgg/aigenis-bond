"""V3 schema: model_versions, training_runs, predictions, portfolio_positions, rebalance_history

Revision ID: 0003_v3
Revises: 0002_v2
Create Date: 2026-06-18 18:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_v3"
down_revision: str | None = "0002_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column("version", sa.String(length=64), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "metrics",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "trained_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("train_rows", sa.Integer(), nullable=False),
        sa.Column("artifact_path", sa.String(length=512), nullable=False),
        sa.Column("notes", sa.String(length=1024), nullable=True),
    )
    op.create_index("ix_model_versions_kind", "model_versions", ["kind"])

    op.create_table(
        "training_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "metrics",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("notes", sa.String(length=1024), nullable=True),
    )
    op.create_index("ix_training_runs_started", "training_runs", ["started_at"])
    op.create_index("ix_training_runs_version", "training_runs", ["version"])

    op.create_table(
        "predictions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("internal_id", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("asof_date", sa.Date(), nullable=False),
        sa.Column("predicted_ytm", sa.Numeric(10, 4), nullable=True),
        sa.Column("predicted_return_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("predicted_volatility", sa.Numeric(10, 4), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column(
            "feature_importance",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "explanation",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_predictions_internal_id", "predictions", ["internal_id"])
    op.create_index("ix_predictions_asof", "predictions", ["asof_date"])
    op.create_index("ix_predictions_decision", "predictions", ["decision"])

    op.create_table(
        "portfolio_positions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("internal_id", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("current_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("current_yield", sa.Numeric(10, 4), nullable=True),
        sa.UniqueConstraint("user_id", "internal_id", name="uq_position_user_bond"),
    )
    op.create_index("ix_positions_user_id", "portfolio_positions", ["user_id"])

    op.create_table(
        "rebalance_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("drift_threshold", sa.Numeric(5, 4), nullable=False),
        sa.Column("max_drift_observed", sa.Numeric(5, 4), nullable=False),
        sa.Column("expected_return", sa.Numeric(10, 4), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(20, 4), nullable=True),
        sa.Column(
            "actions",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_rebalance_user", "rebalance_history", ["user_id"])
    op.create_index("ix_rebalance_created", "rebalance_history", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_rebalance_created", table_name="rebalance_history")
    op.drop_index("ix_rebalance_user", table_name="rebalance_history")
    op.drop_table("rebalance_history")

    op.drop_index("ix_positions_user_id", table_name="portfolio_positions")
    op.drop_table("portfolio_positions")

    op.drop_index("ix_predictions_decision", table_name="predictions")
    op.drop_index("ix_predictions_asof", table_name="predictions")
    op.drop_index("ix_predictions_internal_id", table_name="predictions")
    op.drop_table("predictions")

    op.drop_index("ix_training_runs_version", table_name="training_runs")
    op.drop_index("ix_training_runs_started", table_name="training_runs")
    op.drop_table("training_runs")

    op.drop_index("ix_model_versions_kind", table_name="model_versions")
    op.drop_table("model_versions")
