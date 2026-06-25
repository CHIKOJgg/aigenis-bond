"""V4 schema: curve_points, rv_signals, carry_trades, repo_deals, stress_runs

Revision ID: 0004_v4
Revises: 0003_v3
Create Date: 2026-06-18 21:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_v4"
down_revision: str | None = "0003_v3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "curve_points",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("tenor", sa.String(length=8), nullable=False),
        sa.Column("years", sa.Numeric(8, 4), nullable=False),
        sa.Column("rate_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "ns_params",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )
    op.create_index("ix_curve_currency_date", "curve_points", ["currency", "observed_at"])

    op.create_table(
        "rv_signals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("internal_id", sa.String(length=64), nullable=False),
        sa.Column("peer_currency", sa.String(length=8), nullable=False),
        sa.Column("z_score", sa.Numeric(8, 4), nullable=False),
        sa.Column("spread_pct", sa.Numeric(8, 4), nullable=False),
        sa.Column("fair_spread_pct", sa.Numeric(8, 4), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("rationale", sa.String(length=512), nullable=False),
        sa.Column("asof_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_rv_internal_id", "rv_signals", ["internal_id"])
    op.create_index("ix_rv_asof", "rv_signals", ["asof_date"])
    op.create_index("ix_rv_side", "rv_signals", ["side"])

    op.create_table(
        "carry_trades",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("internal_id", sa.String(length=64), nullable=False),
        sa.Column("notional", sa.Numeric(20, 4), nullable=False),
        sa.Column("coupon_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("funding_rate_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("rolldown_bps", sa.Numeric(10, 4), nullable=False),
        sa.Column("expected_pnl_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("breakeven_bps", sa.Numeric(10, 4), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("asof_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_carry_internal_id", "carry_trades", ["internal_id"])
    op.create_index("ix_carry_asof", "carry_trades", ["asof_date"])

    op.create_table(
        "repo_deals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("internal_id", sa.String(length=64), nullable=False),
        sa.Column("notional", sa.Numeric(20, 4), nullable=False),
        sa.Column("haircut_pct", sa.Numeric(5, 4), nullable=False),
        sa.Column("repo_rate_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("tenor_days", sa.Integer(), nullable=False),
        sa.Column("cash_lent", sa.Numeric(20, 4), nullable=False),
        sa.Column("collateral_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("accrued_interest", sa.Numeric(20, 4), nullable=False),
        sa.Column("asof_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_repo_internal_id", "repo_deals", ["internal_id"])

    op.create_table(
        "stress_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scenario_name", sa.String(length=64), nullable=False),
        sa.Column("scenario_kind", sa.String(length=32), nullable=False),
        sa.Column(
            "scenario",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        sa.Column("portfolio_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("stressed_value", sa.Numeric(20, 4), nullable=False),
        sa.Column("pnl", sa.Numeric(20, 4), nullable=False),
        sa.Column("pnl_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column(
            "by_position",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "by_tenor",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("asof_date", sa.Date(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_stress_name", "stress_runs", ["scenario_name"])
    op.create_index("ix_stress_asof", "stress_runs", ["asof_date"])


def downgrade() -> None:
    op.drop_index("ix_stress_asof", table_name="stress_runs")
    op.drop_index("ix_stress_name", table_name="stress_runs")
    op.drop_table("stress_runs")

    op.drop_index("ix_repo_internal_id", table_name="repo_deals")
    op.drop_table("repo_deals")

    op.drop_index("ix_carry_asof", table_name="carry_trades")
    op.drop_index("ix_carry_internal_id", table_name="carry_trades")
    op.drop_table("carry_trades")

    op.drop_index("ix_rv_side", table_name="rv_signals")
    op.drop_index("ix_rv_asof", table_name="rv_signals")
    op.drop_index("ix_rv_internal_id", table_name="rv_signals")
    op.drop_table("rv_signals")

    op.drop_index("ix_curve_currency_date", table_name="curve_points")
    op.drop_table("curve_points")
