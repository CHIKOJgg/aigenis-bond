"""Add payment_channel to users and key_fp fingerprint to partner_api_keys.

Revision ID: 0019_partner_key_fp
Revises: 0018_fix_numeric_precision

* ``users.payment_channel`` — which billing provider actually paid
  (yookassa | stars), introduced with cross-channel protections.
* ``partner_api_keys.key_fp`` — fast SHA-256 fingerprint lookup for API key
  auth (see api/partner/security.py). Existing rows are backfilled with a
  deterministic pseudo-fingerprint derived from ``key_hash`` so that the
  indexed lookup finds them; the authoritative bcrypt verification in
  ``verify_api_key`` is unaffected and existing partner keys keep working.
"""

from __future__ import annotations

import hashlib

import sqlalchemy as sa

from alembic import op

revision = "0019_partner_key_fp"
down_revision = "0018_fix_numeric_precision"
branch_labels = None
depends_on = None


def _legacy_fingerprint(key_hash: str) -> str:
    return hashlib.sha256(("legacy:" + key_hash).encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column("users", sa.Column("payment_channel", sa.String(16), nullable=True))

    op.add_column("partner_api_keys", sa.Column("key_fp", sa.String(64), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, key_hash FROM partner_api_keys WHERE key_fp IS NULL")
    ).fetchall()
    for key_id, key_hash in rows:
        bind.execute(
            sa.text("UPDATE partner_api_keys SET key_fp = :fp WHERE id = :id"),
            {"fp": _legacy_fingerprint(key_hash), "id": key_id},
        )
    # SQLite cannot ALTER COLUMN to NOT NULL — batch mode recreates the table
    # (with FK enforcement off during rebuild), which is portable to PG too.
    with op.batch_alter_table("partner_api_keys") as batch:
        batch.alter_column("key_fp", existing_type=sa.String(64), nullable=False)
    op.create_index("ix_partner_api_keys_key_fp", "partner_api_keys", ["key_fp"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_partner_api_keys_key_fp", table_name="partner_api_keys")
    op.drop_column("partner_api_keys", "key_fp")
    op.drop_column("users", "payment_channel")
