"""Partner API surface: key management, webhooks, and read-only analytics.

Mounted at ``/api/v1/partner``. Key-management endpoints use the normal user
JWT (so a Pro/Enterprise user can mint B2B keys); the data/webhook endpoints
use the partner API key (``X-Aigenis-Api-Key``) and are quota-limited per key.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from api import _helpers as _h
from api.access_control import _get_current_user_from_request
from api.analytics import _get_bond_or_404, _score_for_bond
from api.i18n import get_lang, tr
from api.partner.security import generate_api_key, partner_rate_limit
from api.partner.webhooks import (
    SUPPORTED_EVENTS,
    delete_webhook,
    emit_webhook_event,
    list_webhooks,
    register_webhook,
)
from desk import relative_value as desk_rv
from ml.repository import predictions_for_bond
from scoring.disclaimer import DISCLAIMER_FULL
from scoring.explain import explain_score
from scraper.db import session_scope
from scraper.orm import BondORM, PartnerKeyORM, WebhookORM

router = APIRouter(prefix="/api/v1/partner", tags=["partner"])


# --- Auth bridge for per-request localization --------------------------------
def _lang(request: Request) -> str:
    return get_lang(request)


async def _require_user(request: Request) -> int:
    """Resolve the authenticated user from the JWT (used for key management)."""
    user_id = _get_current_user_from_request(request)
    if not user_id:
        raise HTTPException(status_code=401, detail=tr(get_lang(request), "not_authenticated"))
    return user_id


# --------------------------------------------------------------------------- #
# Key management (user JWT)
# --------------------------------------------------------------------------- #
class CreateKeyRequest(BaseModel):
    name: str


class CreateKeyResponse(BaseModel):
    id: int
    name: str
    api_key: str  # returned only once
    tier: str
    rate_limit: int


class KeyInfo(BaseModel):
    id: int
    name: str
    tier: str
    rate_limit: int
    active: bool
    created_at: str | None


@router.post("/keys", response_model=CreateKeyResponse, status_code=201)
async def create_partner_key(
    body: CreateKeyRequest,
    user_id: int = Depends(_require_user),
):
    raw, key_hash = generate_api_key()
    async with session_scope() as session:
        key = PartnerKeyORM(
            name=body.name,
            owner_user_id=user_id,
            key_hash=key_hash,
            tier="partner",
            rate_limit=120,
            active=True,
        )
        session.add(key)
        await session.commit()
        await session.refresh(key)
    return CreateKeyResponse(
        id=key.id, name=key.name, api_key=raw,
        tier=key.tier, rate_limit=key.rate_limit,
    )


@router.get("/keys", response_model=list[KeyInfo])
async def list_partner_keys(user_id: int = Depends(_require_user)):
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(PartnerKeyORM).where(PartnerKeyORM.owner_user_id == user_id)
            )
        ).scalars().all()
        return [
            KeyInfo(
                id=k.id, name=k.name, tier=k.tier, rate_limit=k.rate_limit,
                active=k.active,
                created_at=k.created_at.isoformat() if k.created_at else None,
            )
            for k in rows
        ]


@router.delete("/keys/{key_id}", response_model=dict)
async def revoke_partner_key(key_id: int, request: Request, user_id: int = Depends(_require_user)):
    async with session_scope() as session:
        key = (
            await session.execute(
                select(PartnerKeyORM).where(
                    PartnerKeyORM.id == key_id,
                    PartnerKeyORM.owner_user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if key is None:
            raise HTTPException(status_code=404, detail="Key not found")
        key.active = False
        key.revoked_at = datetime.now(UTC)
        await session.commit()
    lang = _lang(request)
    return {"ok": True, "message": tr(lang, "key_revoked")}


# --------------------------------------------------------------------------- #
# Webhooks (partner key)
# --------------------------------------------------------------------------- #
class RegisterWebhookRequest(BaseModel):
    url: str
    events: list[str]


class WebhookInfo(BaseModel):
    id: int
    url: str
    events: list[str]
    active: bool
    created_at: str | None
    last_error: str | None
    last_delivered_at: str | None
    message: str | None = None


@router.post("/webhooks", response_model=WebhookInfo, status_code=201)
async def create_webhook(
    body: RegisterWebhookRequest,
    request: Request,
    key: PartnerKeyORM = Depends(partner_rate_limit),
):
    lang = _lang(request)
    if not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail=tr(lang, "invalid_url"))
    bad = [e for e in body.events if e not in SUPPORTED_EVENTS]
    if bad:
        raise HTTPException(status_code=400, detail=tr(lang, "event_unsupported", event=", ".join(bad)))
    secret = secrets.token_urlsafe(24)
    wh = await register_webhook(
        partner_key_id=key.id, url=body.url, events=body.events, secret=secret
    )
    return _webhook_info(wh, tr(lang, "webhook_registered"))


@router.get("/webhooks", response_model=list[WebhookInfo])
async def get_webhooks(key: PartnerKeyORM = Depends(partner_rate_limit)):
    rows = await list_webhooks(key.id)
    return [_webhook_info(w) for w in rows]


@router.delete("/webhooks/{webhook_id}", response_model=dict)
async def remove_webhook(
    webhook_id: int, request: Request, key: PartnerKeyORM = Depends(partner_rate_limit)
):
    lang = _lang(request)
    ok = await delete_webhook(key.id, webhook_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"ok": True, "message": tr(lang, "webhook_deleted")}


@router.post("/events/test", response_model=dict)
async def test_event(request: Request, key: PartnerKeyORM = Depends(partner_rate_limit)):
    lang = _lang(request)
    rows = await list_webhooks(key.id)
    subscribed = [w for w in rows if "bond.updated" in (w.events or [])]
    count = 0
    if subscribed:
        count = await emit_webhook_event(
            "bond.updated",
            {"test": True, "partner_key_id": key.id},
            wait=True,
        )
    return {"ok": True, "dispatched": count, "message": tr(lang, "event_dispatched", count=count)}


# --------------------------------------------------------------------------- #
# Read-only analytics (partner key)
# --------------------------------------------------------------------------- #
@router.get("/bonds")
async def list_partner_bonds(
    currency: str | None = None,
    limit: int = Query(20, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    _key: PartnerKeyORM = Depends(partner_rate_limit),
):
    async with session_scope() as session:
        stmt = select(BondORM)
        if currency:
            stmt = stmt.where(BondORM.currency == currency.upper())
        stmt = stmt.limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()
    return [_h.bond_facts(_h.orm_to_bond(b)) for b in rows]


@router.get("/bonds/{internal_id}")
async def partner_bond_detail(internal_id: str, _key: PartnerKeyORM = Depends(partner_rate_limit)):
    bond = await _get_bond_or_404(internal_id)
    score = await _score_for_bond(bond)
    return {
        "bond": _h.bond_facts(bond),
        "score": round(float(score.score), 2),
        "tier": score.tier,
    }


@router.get("/bonds/{internal_id}/analysis")
async def partner_bond_analysis(internal_id: str, _key: PartnerKeyORM = Depends(partner_rate_limit)):
    bond = await _get_bond_or_404(internal_id)
    score = await _score_for_bond(bond)
    ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity else None
    explained = explain_score(score, currency=bond.currency, ytm_pct=ytm)

    all_bonds = [
        _h.orm_to_bond(b)
        async for b in _iter_bonds()
    ]
    rv_signal = None
    for s in desk_rv.relative_value_signals(all_bonds):
        if s.internal_id == internal_id:
            rv_signal = {
                "side": s.side,
                "z_score": round(float(s.z_score), 3) if s.z_score is not None else None,
                "spread_pct": round(float(s.spread_pct), 3) if s.spread_pct is not None else None,
            }
            break

    ml_prediction = None
    async with session_scope() as session:
        rows = await predictions_for_bond(session, internal_id, limit=1)
    if rows:
        p = rows[0]
        ml_prediction = {
            "decision": p.decision,
            "confidence": round(float(p.confidence), 3),
            "predicted_ytm": float(p.predicted_ytm) if p.predicted_ytm is not None else None,
            "predicted_return_pct": float(p.predicted_return_pct)
            if p.predicted_return_pct is not None
            else None,
            "explanation": p.explanation or [],
        }

    return {
        "bond": _h.bond_facts(bond),
        "analysis": explained.as_dict(),
        "relative_value": rv_signal,
        "ml_prediction": ml_prediction,
        "disclaimer": DISCLAIMER_FULL,
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _iter_bonds():
    async with session_scope() as session:
        rows = (await session.execute(select(BondORM))).scalars().all()
        for b in rows:
            yield _h.orm_to_bond(b)


def _webhook_info(w: WebhookORM, message: str | None = None) -> dict:
    data = {
        "id": w.id,
        "url": w.url,
        "events": list(w.events or []),
        "active": w.active,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "last_error": w.last_error,
        "last_delivered_at": w.last_delivered_at.isoformat() if w.last_delivered_at else None,
    }
    if message is not None:
        data["message"] = message
    return data
