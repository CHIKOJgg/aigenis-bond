"""Add branding column to partner_api_keys.

Revision ID: abc123456789
Revises: f6a1b2c3d4e5
Create Date: 2026-07-27

Adds ``branding`` JSON column to ``partner_api_keys`` for white-label
customization (logo URL, primary color, domain, custom CTA).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "abc123456789"
down_revision = "f6a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "partner_api_keys",
        sa.Column(
            "branding",
            JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("partner_api_keys", "branding")