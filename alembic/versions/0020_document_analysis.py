"""
Document analysis persistence.

Revision ID: 0020_document_analysis
Revises: 0019_partner_key_fp
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020_document_analysis"
down_revision = "0019_partner_key_fp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_analysis",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("filename", sa.String(length=256), nullable=False),
        sa.Column("internal_id", sa.String(length=64), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column(
            "extracted_data",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "risk_flags",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_documents_user_created", "document_analysis", ["user_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_documents_user_created", table_name="document_analysis")
    op.drop_table("document_analysis")
