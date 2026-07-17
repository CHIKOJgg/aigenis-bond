"""add companies table

Revision ID: 0010_companies
Revises: 0009_issuer_logo
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_companies"
down_revision = "0009_issuer_logo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("description", sa.String(length=2048), nullable=True),
        sa.Column("why_important", sa.String(length=1024), nullable=True),
        sa.Column("website", sa.String(length=512), nullable=True),
        sa.Column("logo_url", sa.String(length=512), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("issuer"),
    )
    op.create_index("ix_companies_sector", "companies", ["sector"])
    op.create_index("ix_companies_name", "companies", ["name"])


def downgrade() -> None:
    op.drop_index("ix_companies_name", table_name="companies")
    op.drop_index("ix_companies_sector", table_name="companies")
    op.drop_table("companies")
