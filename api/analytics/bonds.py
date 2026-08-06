"""Bonds catalog endpoints: market overview, bond card, analysis, cashflow, history.

Thin HTTP layer: validation and wiring only — use cases live in
``api.services.bonds.BondService``.
"""

from __future__ import annotations

from fastapi import Depends, Query

from api.access_control import RequireFeature, get_current_tier
from api.analytics import router
from api.services import BondService


# --------------------------------------------------------------------------- #
# Free: subscription info (Telegram Stars + YooKassa).
# --------------------------------------------------------------------------- #
@router.get("/subscribe-info")
async def api_subscribe_info():
    return await BondService.subscribe_info()


# --------------------------------------------------------------------------- #
# Free: market overview
# --------------------------------------------------------------------------- #
@router.get("/top")
async def api_top(limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0)):
    return await BondService.top(limit=limit, offset=offset)


@router.get("/bonds/currency/{currency}")
async def api_bonds_by_currency(currency: str):
    return await BondService.by_currency(currency)


# --------------------------------------------------------------------------- #
# Free / Pro: Single-bond deep-dive card ("should I buy this bond?")
# --------------------------------------------------------------------------- #
@router.get("/bond/{internal_id}", dependencies=[Depends(RequireFeature("access_bond_detail"))])
async def api_bond_card(
    internal_id: str,
    tier: str = Depends(get_current_tier),
):
    return await BondService.card(internal_id, tier)


@router.get(
    "/bond/{internal_id}/analysis",
    dependencies=[Depends(RequireFeature("access_bond_analysis"))],
)
async def api_bond_analysis(internal_id: str):
    return await BondService.analysis(internal_id)


@router.get(
    "/bond/{internal_id}/cashflow",
    dependencies=[Depends(RequireFeature("access_portfolio"))],
)
async def api_bond_cashflow(
    internal_id: str,
    amount: float = Query(1000.0, gt=0),
):
    return await BondService.cashflow(internal_id, amount)


@router.get(
    "/bond/{internal_id}/history",
    dependencies=[Depends(RequireFeature("access_bond_analysis"))],
)
async def api_bond_history(internal_id: str, months: int = Query(12, ge=1, le=120)):
    return await BondService.history(internal_id, months)
