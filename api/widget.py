"""Public, unauthenticated bond widget for SEO / partner iframes.

Exposes a small read-only "top bonds" payload that the marketing site and
partner blogs can embed via an <iframe> (see ``WidgetPage``). All endpoints are
public and intentionally limited to non-sensitive fields so the product acts as
a free acquisition magnet with a clear upgrade path.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from scraper.db import session_scope
from scraper.orm import BondORM, BondScoreORM

router = APIRouter(prefix="/widget", tags=["widget"])

# Framing is enabled only for this router (see api.main where the global
# CSP sets frame-ancestors 'none'). Keep the payloads public-only.
_ALLOWED_FRAMING = True


class WidgetBond(BaseModel):
    internal_id: str
    name: str
    currency: str
    yield_to_maturity: float | None = None
    maturity_date: str | None = None
    issuer: str | None = None
    score: float | None = None
    tier: str | None = None


@router.get("/top", response_model=list[WidgetBond])
async def widget_top(limit: int = 10, currency: str | None = None) -> list[WidgetBond]:
    """Top bonds by score, public and unauthenticated (free acquisition magnet)."""
    if limit < 1 or limit > 50:
        limit = 10
    async with session_scope() as session:
        score_stmt = select(BondScoreORM).order_by(BondScoreORM.score.desc()).limit(limit)
        scores = list((await session.execute(score_stmt)).scalars().all())
        if not scores:
            return []
        ids = [s.internal_id for s in scores]
        bond_stmt = select(BondORM).where(BondORM.internal_id.in_(ids))
        if currency:
            bond_stmt = bond_stmt.where(BondORM.currency == currency.upper())
        bonds = {b.internal_id: b for b in (await session.execute(bond_stmt)).scalars().all()}
        score_map = {s.internal_id: s for s in scores}
        out: list[WidgetBond] = []
        for iid in ids:
            bond = bonds.get(iid)
            sc = score_map.get(iid)
            if bond is None:
                continue
            out.append(
                WidgetBond(
                    internal_id=bond.internal_id,
                    name=bond.name,
                    currency=bond.currency,
                    yield_to_maturity=(
                        float(bond.yield_to_maturity) if bond.yield_to_maturity is not None else None
                    ),
                    maturity_date=bond.maturity_date.isoformat() if bond.maturity_date else None,
                    issuer=bond.issuer,
                    score=float(sc.score) if sc and sc.score else None,
                    tier=sc.tier if sc else None,
                )
            )
    return out


@router.get("/embed.js")
async def widget_embed_js(request: Request):
    """Tiny JS snippet partners paste to inject the iframe on their site."""
    origin = str(request.base_url).rstrip("/")
    script = (
        "(function(){"
        "var s=document.currentScript||{};"
        "var base=s&&s.getAttribute?(''+s.src).replace(/\\/embed\\.js.*$/,'')||window.location.origin:'';"
        "var base=base||'" + origin + "';"
        "var frame=document.createElement('iframe');"
        "frame.src=base+'/widget?origin='+encodeURIComponent(window.location.origin);"
        "frame.style.width='100%';frame.style.border='0';frame.style.minHeight='480px';"
        "frame.loading='lazy';"
        "var p=s&&s.parentNode;if(p){p.insertBefore(frame,s);}else{document.body.appendChild(frame);}"
        "})();"
    )
    return JSONResponse(
        content=script,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )
