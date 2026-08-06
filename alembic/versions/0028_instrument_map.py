"""
instrument_map + snapshot_lineage tables (Aigenis integration boundary).

- ``instrument_map`` — версионированная таблица соответствия идентификаторов
  инструментов (aigenis_instrument_id ↔ isin ↔ external_ticker ↔
  analytics_internal_id), Finalplan §13.6 / plan item 5.14.
- ``snapshot_lineage`` — происхождение данных каждого ingestion snapshot
  (source, license/contract_id, as_of, ingestion_run, quality_status),
  plan item 5.6.

Revision ID: 0028_instrument_map
Revises: a1b2c3d4e5f6
Create Date: 2026-08-06
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0028_instrument_map"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instrument_map",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("aigenis_instrument_id", sa.String(length=64), nullable=False),
        sa.Column("isin", sa.String(length=32), nullable=True),
        sa.Column("external_ticker", sa.String(length=64), nullable=True),
        sa.Column("market", sa.String(length=8), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("analytics_internal_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.BigInteger(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_instrument_map_aigenis_id_version",
        "instrument_map",
        ["aigenis_instrument_id", "version"],
        unique=True,
    )
    op.create_index(
        "ix_instrument_map_aigenis_id", "instrument_map", ["aigenis_instrument_id"], unique=False
    )
    op.create_index("ix_instrument_map_isin", "instrument_map", ["isin"], unique=False)
    op.create_index(
        "ix_instrument_map_internal_id", "instrument_map", ["analytics_internal_id"], unique=False
    )

    op.create_table(
        "snapshot_lineage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("license_contract_id", sa.String(length=64), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingestion_run", sa.String(length=64), nullable=True),
        sa.Column("quality_status", sa.String(length=16), server_default="ok", nullable=False),
        sa.Column("market", sa.String(length=8), nullable=True),
        sa.Column("rows_processed", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_snapshot_lineage_run", "snapshot_lineage", ["ingestion_run"], unique=False)
    op.create_index("ix_snapshot_lineage_as_of", "snapshot_lineage", ["as_of"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_snapshot_lineage_as_of", table_name="snapshot_lineage")
    op.drop_index("ix_snapshot_lineage_run", table_name="snapshot_lineage")
    op.drop_table("snapshot_lineage")
    op.drop_index("ix_instrument_map_internal_id", table_name="instrument_map")
    op.drop_index("ix_instrument_map_isin", table_name="instrument_map")
    op.drop_index("ix_instrument_map_aigenis_id", table_name="instrument_map")
    op.drop_index("uq_instrument_map_aigenis_id_version", table_name="instrument_map")
    op.drop_table("instrument_map")
