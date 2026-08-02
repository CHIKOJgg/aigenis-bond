"""
Unique constraint on predictions (internal_id, asof_date, model_version, kind).

Fixes upsert_predictions (ml/repository.py): ON CONFLICT requires a matching
unique constraint on PostgreSQL; without it every `ml-predict` run failed.

Revision ID: 0023_predictions_unique
Revises: 0022_spread_reports
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0023_predictions_unique"
down_revision = "0022_spread_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Deduplicate existing rows (keep the earliest id per key) so the unique
    # constraint can be created on live databases. The subquery form works on
    # both PostgreSQL and SQLite.
    op.execute(
        """
        DELETE FROM predictions
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM predictions
            GROUP BY internal_id, asof_date, model_version, kind
        )
        """
    )
    with op.batch_alter_table("predictions", recreate="auto") as batch:
        batch.create_unique_constraint(
            "uq_predictions_key",
            ["internal_id", "asof_date", "model_version", "kind"],
        )


def downgrade() -> None:
    with op.batch_alter_table("predictions", recreate="auto") as batch:
        batch.drop_constraint("uq_predictions_key", type_="unique")
