"""fix fallback bond market tagging

The MOEX ISS fallback adapter (scraper/fallback_source.py) returns bonds
without an explicit ``market`` field, and the fallback ingestion path in
scraper/pipeline.py inserted them without one — so PostgreSQL's
``server_default='bcse'`` stamped every fallback (MOEX) bond as BCSE.

That leaked Russian MOEX bonds (ДОМ.РФ, ВЭБ.РФ, Западный скоростной
диаметр, Северо-Западная концессионная компания, ...) into the BCSE
segment of the demo (stress tests, curve, search).

The ingestion code is fixed to always set ``market`` explicitly; this
migration re-tags the rows that were already written with the wrong market.

Revision ID: 0030_fix_fallback_bond_market
Revises: 0029_job_runs
Create Date: 2026-08-14 21:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0030_fix_fallback_bond_market"
down_revision: str | None = "0029_job_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fallback adapter names bonds MOEX_<SECID>; anything stored as BCSE
    # under that prefix was mis-tagged via server_default.
    op.execute(
        "UPDATE bonds SET market = 'moex' "
        "WHERE market = 'bcse' AND internal_id LIKE 'MOEX_%'"
    )


def downgrade() -> None:
    # No schema change to revert; the data fix is intentionally one-way.
    pass
