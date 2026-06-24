"""init schema: bonds, bond_history, parse_errors

Revision ID: 0001_init
Revises:
Create Date: 2026-06-18 00:00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bonds",
        sa.Column("internal_id", sa.String(length=64), primary_key=True),
        sa.Column("isin", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("nominal", sa.Numeric(20, 6), nullable=True),
        sa.Column("coupon_rate", sa.Numeric(10, 4), nullable=True),
        sa.Column("coupon_frequency", sa.Integer(), nullable=True),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("price", sa.Numeric(20, 6), nullable=True),
        sa.Column("yield_to_maturity", sa.Numeric(10, 4), nullable=True),
        sa.Column("amortization", sa.String(length=16), nullable=True),
        sa.Column("offer_date", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column(
            "raw",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("isin", name="uq_bonds_isin"),
    )
    op.create_index("ix_bonds_currency", "bonds", ["currency"])
    op.create_index("ix_bonds_status", "bonds", ["status"])
    op.create_index("ix_bonds_yield_desc", "bonds", ["yield_to_maturity"])
    op.create_index("ix_bonds_maturity", "bonds", ["maturity_date"])

    op.create_table(
        "bond_history",
        sa.Column(
            "internal_id",
            sa.String(length=64),
            sa.ForeignKey("bonds.internal_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("price", sa.Numeric(20, 6), nullable=True),
        sa.Column("yield", sa.Numeric(10, 4), nullable=True),
        sa.Column("coupon", sa.Numeric(10, 4), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unknown"),
    )
    op.create_index("ix_history_id_date", "bond_history", ["internal_id", "date"])

    op.create_table(
        "parse_errors",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("internal_id", sa.String(length=64), nullable=True),
        sa.Column("error_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.String(length=2048), nullable=False),
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
    )
    op.create_index("ix_errors_internal_id", "parse_errors", ["internal_id"])
    op.create_index("ix_errors_created_at", "parse_errors", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_errors_created_at", table_name="parse_errors")
    op.drop_index("ix_errors_internal_id", table_name="parse_errors")
    op.drop_table("parse_errors")

    op.drop_index("ix_history_id_date", table_name="bond_history")
    op.drop_table("bond_history")

    op.drop_index("ix_bonds_maturity", table_name="bonds")
    op.drop_index("ix_bonds_yield_desc", table_name="bonds")
    op.drop_index("ix_bonds_status", table_name="bonds")
    op.drop_index("ix_bonds_currency", table_name="bonds")
    op.drop_table("bonds")
