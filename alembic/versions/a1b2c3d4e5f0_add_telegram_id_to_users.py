"""add telegram_id to users

Revision ID: a1b2c3d4e5f0
Revises: c845972200a0
Create Date: 2026-07-10 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a1b2c3d4e5f0'
down_revision: str | None = 'c845972200a0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('users', sa.Column('telegram_id', sa.BigInteger(), nullable=True))
    op.create_index('ix_users_telegram_id', 'users', ['telegram_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_telegram_id', table_name='users')
    op.drop_column('users', 'telegram_id')
