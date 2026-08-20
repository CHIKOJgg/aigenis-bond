"""add order book bid/ask columns to bonds

Persist the real order book (best bid / best offer and their yields) so the
product can display quotes like the live Aigenis stakan instead of a single
mid price. The Aigenis client already fetches ``best_bid`` / ``best_offer`` /
``calc_yield_bid`` / ``calc_yield_offer`` but they were discarded because the
model only stored one ``price`` / ``yield_to_maturity``.

Revision ID: 0031_bond_order_book
Revises: 0030_fix_fallback_bond_market
Create Date: 2026-08-20 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_bond_order_book"
down_revision: str = "0030_fix_fallback_bond_market"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bonds",
        sa.Column("bid", sa.Numeric(20, 6), nullable=True),
    )
    op.add_column(
        "bonds",
        sa.Column("ask", sa.Numeric(20, 6), nullable=True),
    )
    op.add_column(
        "bonds",
        sa.Column("bid_yield", sa.Numeric(14, 4), nullable=True),
    )
    op.add_column(
        "bonds",
        sa.Column("ask_yield", sa.Numeric(14, 4), nullable=True),
    )
    op.create_index("ix_bonds_bid", "bonds", ["bid"])
    op.create_index("ix_bonds_ask", "bonds", ["ask"])


def downgrade() -> None:
    op.drop_index("ix_bonds_ask", table_name="bonds")
    op.drop_index("ix_bonds_bid", table_name="bonds")
    op.drop_column("bonds", "ask_yield")
    op.drop_column("bonds", "bid_yield")
    op.drop_column("bonds", "ask")
    op.drop_column("bonds", "bid")
