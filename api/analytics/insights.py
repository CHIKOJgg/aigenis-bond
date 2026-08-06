"""Insights endpoints: recommendations, companies, search, ML status/predictions."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select

from api import _helpers as _h
from api.access_control import RequireFeature
from api.analytics import router
from api.analytics._helpers import _all_bonds
from ml.repository import latest_model_version, predictions_for_bond
from recommendations.engine import recommend_bonds, recommend_for_issuer
from scoring.disclaimer import DISCLAIMER_FULL
from scraper.db import session_scope
from scraper.orm import BondORM, BondScoreORM, CompanyORM


@router.get("/recommendations", dependencies=[Depends(RequireFeature("access_recommendations"))])
async def api_recommendations(top_k: int = Query(5, ge=1, le=20)):
    bonds = await _all_bonds()
    bond_dicts = [
        {
            "internal_id": b.internal_id,
            "name": b.name,
            "currency": b.currency,
            "yield_to_maturity": b.yield_to_maturity,
            "coupon_rate": b.coupon_rate,
            "maturity_date": b.maturity_date,
            "price": b.price,
            "status": b.status,
            "issuer": b.issuer,
        }
        for b in bonds
    ]
    prefs = _h.default_prefs(0)
    recs = recommend_bonds(bond_dicts, prefs, history_by_bond={}, top_k=top_k)
    issuer_by_id = {b["internal_id"]: b.get("issuer") for b in bond_dicts}
    return [
        {
            "rank": r.rank,
            "internal_id": r.internal_id,
            "name": r.name,
            "issuer": issuer_by_id.get(r.internal_id),
            "decision": r.decision,
            "confidence": round(float(r.confidence), 3),
            "score": round(float(r.score), 2) if r.score is not None else None,
            "predicted_return_pct": round(float(r.predicted_return_pct), 3)
            if r.predicted_return_pct is not None
            else None,
            "reasons": r.reasons,
            "risks": r.risks,
        }
        for r in recs
    ]


@router.get("/companies")
async def api_companies(
    sector: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Топ эмитентов (компаний) с агрегатами по их облигациям.

    Бесплатно: базовая детализация рынка. Агрегаты (число выпусков, средний
    YTM, средний тир) считаются на лету из ``bonds`` и ``bond_scores``.
    """
    async with session_scope() as session:
        comp_rows = (await session.execute(select(CompanyORM))).scalars().all()
        companies = {c.issuer: c for c in comp_rows}
        bond_rows = (await session.execute(select(BondORM))).scalars().all()
        score_rows = (await session.execute(select(BondScoreORM))).scalars().all()
        scores_by_id = {s.internal_id: s for s in score_rows}

    by_issuer: dict[str, list[BondORM]] = {}
    for b in bond_rows:
        if b.issuer:
            by_issuer.setdefault(b.issuer, []).append(b)

    out = []
    for issuer, bs in by_issuer.items():
        if sector:
            comp = companies.get(issuer)
            if not comp or comp.sector != sector:
                continue
        ytms = [float(b.yield_to_maturity) for b in bs if b.yield_to_maturity is not None]
        tiers = [
            scores_by_id[b.internal_id].tier
            for b in bs
            if b.internal_id in scores_by_id and scores_by_id[b.internal_id].tier
        ]
        avg_ytm = round(sum(ytms) / len(ytms), 2) if ytms else None
        comp = companies.get(issuer)
        out.append(
            {
                "issuer": issuer,
                "name": (comp.name if comp and comp.name else issuer) if comp else issuer,
                "sector": comp.sector if comp else None,
                "description": comp.description if comp else None,
                "why_important": comp.why_important if comp else None,
                "logo_url": comp.logo_url if comp else None,
                "bond_count": len(bs),
                "avg_yield_to_maturity": avg_ytm,
                "top_tier": _h.most_common(tiers),
                "currencies": sorted({str(b.currency) for b in bs}),
            }
        )

    out.sort(key=lambda c: (c["bond_count"], c["avg_yield_to_maturity"] or 0), reverse=True)
    return out[:limit]


@router.get("/companies/{issuer}")
async def api_company_detail(issuer: str):
    """Карточка компании-эмитента: описание, агрегаты, облигации, рекомендация.

    Бесплатно. Рекомендация по компании собирается из рекомендаций по её
    выпускам (``recommend_for_issuer``).
    """
    async with session_scope() as session:
        comp = (
            (await session.execute(select(CompanyORM).where(CompanyORM.issuer == issuer)))
            .scalars()
            .one_or_none()
        )
        bond_rows = (
            (await session.execute(select(BondORM).where(BondORM.issuer == issuer))).scalars().all()
        )
        score_rows = (
            (
                await session.execute(
                    select(BondScoreORM).where(
                        BondScoreORM.internal_id.in_([b.internal_id for b in bond_rows])
                    )
                )
            )
            .scalars()
            .all()
        )
        scores_by_id = {s.internal_id: s for s in score_rows}

    if not bond_rows and not comp:
        raise HTTPException(status_code=404, detail=f"Компания '{issuer}' не найдена")

    bonds = [_h.orm_to_bond(b) for b in bond_rows]
    bond_dicts = [
        {
            "internal_id": b.internal_id,
            "name": b.name,
            "currency": b.currency,
            "yield_to_maturity": b.yield_to_maturity,
            "coupon_rate": b.coupon_rate,
            "maturity_date": b.maturity_date,
            "price": b.price,
            "status": b.status,
            "issuer": b.issuer,
        }
        for b in bonds
    ]
    company_rec = None
    if bond_dicts:
        prefs = _h.default_prefs(0)
        rec = recommend_for_issuer(bond_dicts, prefs, history_by_bond={})
        if rec:
            company_rec = {
                "decision": rec.decision,
                "confidence": round(float(rec.confidence), 3),
                "score": round(float(rec.score), 2) if rec.score is not None else None,
                "predicted_return_pct": round(float(rec.predicted_return_pct), 3)
                if rec.predicted_return_pct is not None
                else None,
                "reasons": rec.reasons,
                "risks": rec.risks,
            }

    bond_list = []
    for b in bond_rows:
        s = scores_by_id.get(b.internal_id)
        bond_list.append(
            {
                "internal_id": b.internal_id,
                "name": b.name,
                "currency": b.currency,
                "yield_to_maturity": float(b.yield_to_maturity)
                if b.yield_to_maturity is not None
                else None,
                "maturity_date": b.maturity_date.isoformat() if b.maturity_date else None,
                "price": float(b.price) if b.price is not None else None,
                "issuer": b.issuer,
                "score": float(s.score) if s else None,
                "tier": s.tier if s else None,
            }
        )

    return {
        "issuer": issuer,
        "name": comp.name if comp and comp.name else issuer,
        "sector": comp.sector if comp else None,
        "description": comp.description if comp else None,
        "why_important": comp.why_important if comp else None,
        "website": comp.website if comp else None,
        "logo_url": comp.logo_url if comp else None,
        "bond_count": len(bond_rows),
        "bonds": bond_list,
        "recommendation": company_rec,
    }


@router.get("/search")
async def api_search(q: str = Query(..., min_length=1)):
    """Поиск по облигациям и компаниям (бесплатно).

    Ищет по имени/ISIN/внутреннему ID облигации и по названию/эмитенту/сектору
    компании. Возвращает два списка: ``bonds`` и ``companies``.
    """
    q_lower = q.lower().strip()
    async with session_scope() as session:
        bond_rows = (await session.execute(select(BondORM))).scalars().all()
        comp_rows = (await session.execute(select(CompanyORM))).scalars().all()

    bond_hits = []
    for b in bond_rows:
        haystack = " ".join(str(x) for x in (b.name, b.isin, b.internal_id, b.issuer) if x).lower()
        if q_lower in haystack:
            bond_hits.append(
                {
                    "internal_id": b.internal_id,
                    "name": b.name,
                    "currency": b.currency,
                    "yield_to_maturity": float(b.yield_to_maturity)
                    if b.yield_to_maturity is not None
                    else None,
                    "issuer": b.issuer,
                }
            )
        if len(bond_hits) >= 30:
            break

    comp_hits = []
    for c in comp_rows:
        haystack = " ".join(
            str(x) for x in (c.name, c.issuer, c.sector, c.description) if x
        ).lower()
        if q_lower in haystack:
            comp_hits.append({"issuer": c.issuer, "name": c.name or c.issuer, "sector": c.sector})
        if len(comp_hits) >= 30:
            break

    return {"query": q, "bonds": bond_hits, "companies": comp_hits}


@router.get("/ml/status", dependencies=[Depends(RequireFeature("access_ml"))])
async def api_ml_status():
    async with session_scope() as session:
        mv_reg = await latest_model_version(session, "ytm_regression")
        mv_clf = await latest_model_version(session, "buy_classifier")
    return {
        "ytm_regression": (
            {"version": mv_reg.version, "train_rows": mv_reg.train_rows, "metrics": mv_reg.metrics}
            if mv_reg
            else None
        ),
        "buy_classifier": (
            {"version": mv_clf.version, "train_rows": mv_clf.train_rows, "metrics": mv_clf.metrics}
            if mv_clf
            else None
        ),
    }


@router.get("/ml/predict/{bond_id}", dependencies=[Depends(RequireFeature("access_ml"))])
async def api_ml_predict(bond_id: str):
    async with session_scope() as session:
        rows = await predictions_for_bond(session, bond_id, limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="No prediction for this bond")
    p = rows[0]
    return {
        "internal_id": bond_id,
        "decision": p.decision,
        "confidence": round(float(p.confidence), 3),
        "predicted_ytm": float(p.predicted_ytm) if p.predicted_ytm is not None else None,
        "predicted_return_pct": float(p.predicted_return_pct)
        if p.predicted_return_pct is not None
        else None,
        "explanation": p.explanation or [],
        "disclaimer": DISCLAIMER_FULL,
    }
