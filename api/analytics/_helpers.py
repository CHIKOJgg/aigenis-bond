"""Shared helpers for the analytics API package (api.analytics.*).

Kept importable from ``api.analytics`` for backwards compatibility with
``api/partner/router.py`` (``_get_bond_or_404``, ``_score_for_bond``).
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select

from api import _helpers as _h
from scoring.engine import score_bond
from scoring.repository import get_score, score_from_orm
from scraper.db import session_scope
from scraper.models import Bond
from scraper.orm import BondORM


async def _all_bonds() -> list[Bond]:
    async with session_scope() as session:
        rows = (await session.execute(select(BondORM))).scalars().all()
        return [_h.orm_to_bond(b) for b in rows]


async def _get_bond_or_404(internal_id: str) -> Bond:
    async with session_scope() as session:
        row = (
            await session.execute(select(BondORM).where(BondORM.internal_id == internal_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"Bond {internal_id} not found")
        return _h.orm_to_bond(row)


async def _score_for_bond(b: Bond):
    """Return a BondScore, preferring the stored one (persisted breakdown)."""
    async with session_scope() as session:
        orm = await get_score(session, b.internal_id)
    if orm is not None:
        return score_from_orm(orm)
    return score_bond(
        internal_id=b.internal_id,
        yield_to_maturity=b.yield_to_maturity,
        currency=b.currency,
        maturity_date=b.maturity_date,
        status=b.status,
        issuer=b.issuer,
        price=b.price,
    )
