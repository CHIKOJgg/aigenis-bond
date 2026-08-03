"""
Unique keys for desk tables so daily runs upsert instead of accumulating rows.

Daily scheduled runs (curve / RV / carry / spreads / stress) previously used
plain inserts and grew without bound; spread_reports was also written from a
GET endpoint, amplifying duplicates. Each table now has a natural-key unique
index and desk/repository.py upserts with ON CONFLICT DO UPDATE.

Revision ID: 0027_desk_unique_keys
Revises: 0026_user_referral_code
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0027_desk_unique_keys"
down_revision = "0026_user_referral_code"
branch_labels = None
depends_on = None

_CONFLICT_KEYS = {
    "curve_points": ("currency", "tenor", "day"),
    "rv_signals": ("internal_id", "peer_currency", "asof_date"),
    "carry_trades": ("internal_id", "asof_date"),
    "spread_reports": ("internal_id", "asof_date"),
    "stress_runs": ("scenario_name", "asof_date"),
}


def _dedupe(table: str, keys: list[str]) -> None:
    """Keep the earliest row per natural key (like 0023 did for predictions)."""
    group = ", ".join(keys)
    op.execute(
        f"""
        DELETE FROM {table}
        WHERE id NOT IN (
            SELECT MIN(id) FROM {table} GROUP BY {group}
        )
        """
    )


def upgrade() -> None:
    _dedupe("rv_signals", ["internal_id", "peer_currency", "asof_date"])
    _dedupe("carry_trades", ["internal_id", "asof_date"])
    _dedupe("spread_reports", ["internal_id", "asof_date"])
    _dedupe("stress_runs", ["scenario_name", "asof_date"])
    # curve_points: one point per (currency, tenor, calendar day).
    op.execute(
        """
        DELETE FROM curve_points
        WHERE id NOT IN (
            SELECT MIN(id) FROM curve_points GROUP BY currency, tenor, date(observed_at)
        )
        """
    )

    op.create_index(
        "uq_rv_signal_day",
        "rv_signals",
        ["internal_id", "peer_currency", "asof_date"],
        unique=True,
    )
    op.create_index(
        "uq_carry_day",
        "carry_trades",
        ["internal_id", "asof_date"],
        unique=True,
    )
    op.create_index(
        "uq_spread_day",
        "spread_reports",
        ["internal_id", "asof_date"],
        unique=True,
    )
    op.create_index(
        "uq_stress_day",
        "stress_runs",
        ["scenario_name", "asof_date"],
        unique=True,
    )
    # Expression index works on both PostgreSQL and SQLite. PostgreSQL requires
    # an IMMUTABLE expression: date(timestamptz) depends on the session tz, so
    # cast to date in a fixed zone. SQLite's date() is fine. Built via raw DDL
    # because op.create_index mis-renders text() expression elements.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE UNIQUE INDEX uq_curve_tenor_day ON curve_points "
            "(currency, tenor, ((observed_at AT TIME ZONE 'UTC')::date))"
        )
    else:
        op.execute(
            "CREATE UNIQUE INDEX uq_curve_tenor_day ON curve_points "
            "(currency, tenor, date(observed_at))"
        )


def downgrade() -> None:
    for index in (
        "uq_rv_signal_day",
        "uq_carry_day",
        "uq_spread_day",
        "uq_stress_day",
        "uq_curve_tenor_day",
    ):
        op.drop_index(index, table_name=None)
