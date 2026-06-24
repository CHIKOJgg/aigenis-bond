"""FastAPI REST API для данных по облигациям."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from scraper.db import session_scope
from scraper.orm import BondORM, BondScoreORM

app = FastAPI(title="Aigenis Bonds API", version="1.0.0")


@app.get("/health")
async def health() -> dict[str, str]:
    db_ok = False
    try:
        async with session_scope() as session:
            await session.execute(select(BondORM).limit(1))
            db_ok = True
    except Exception:
        pass
    return {"status": "ok" if db_ok else "degraded"}


@app.get("/api/v1/bonds")
async def list_bonds(
    currency: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    async with session_scope() as session:
        stmt = select(BondORM)
        if currency:
            stmt = stmt.where(BondORM.currency == currency)
        stmt = stmt.limit(limit).offset(offset)
        result = await session.execute(stmt)
        bonds = list(result.scalars().all())
    return [_bond_to_dict(b) for b in bonds]


@app.get("/api/v1/bonds/{internal_id}")
async def get_bond(internal_id: str) -> dict[str, Any]:
    async with session_scope() as session:
        result = await session.execute(
            select(BondORM).where(BondORM.internal_id == internal_id)
        )
        bond = result.scalar_one_or_none()
    if bond is None:
        raise HTTPException(status_code=404, detail="Bond not found")
    return _bond_to_dict(bond)


@app.get("/api/v1/scores")
async def list_scores(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    async with session_scope() as session:
        result = await session.execute(
            select(BondScoreORM).order_by(BondScoreORM.score.desc()).limit(limit).offset(offset)
        )
        scores = list(result.scalars().all())
    return [
        {
            "internal_id": s.internal_id,
            "score": float(s.score) if s.score else 0,
            "tier": s.tier,
        }
        for s in scores
    ]


def _bond_to_dict(b: BondORM) -> dict[str, Any]:
    return {
        "internal_id": b.internal_id,
        "name": b.name,
        "currency": b.currency,
        "price": float(b.price) if b.price else None,
        "yield_to_maturity": float(b.yield_to_maturity) if b.yield_to_maturity else None,
        "coupon_rate": float(b.coupon_rate) if b.coupon_rate else None,
        "coupon_frequency": b.coupon_frequency,
        "maturity_date": b.maturity_date.isoformat() if b.maturity_date else None,
        "status": b.status,
        "issuer": b.issuer,
        "fetched_at": b.fetched_at.isoformat() if b.fetched_at else None,
    }
