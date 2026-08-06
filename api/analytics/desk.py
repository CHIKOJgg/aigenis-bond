"""Desk analytics endpoints: RV, duration, carry, repo, stress, curve, spreads.

Thin HTTP layer: validation and wiring only — use cases live in
``api.services.desk.DeskService``.
"""

from __future__ import annotations

from fastapi import Depends, Query
from pydantic import BaseModel

from api.access_control import RequireFeature
from api.analytics import router
from api.services import DeskService


@router.get("/desk/rv", dependencies=[Depends(RequireFeature("access_desk_rv"))])
async def api_rv():
    return await DeskService.rv()


@router.get("/desk/duration", dependencies=[Depends(RequireFeature("access_desk_rv"))])
async def api_duration(bond_id: str | None = Query(None)):
    return await DeskService.duration(bond_id)


@router.get("/desk/carry", dependencies=[Depends(RequireFeature("access_desk_carry"))])
async def api_carry(funding: float = Query(5.0, ge=0.0)):
    return await DeskService.carry(funding_rate_pct=funding)


class RepoRequest(BaseModel):
    bond_id: str
    notional: float = 1000.0
    tenor_days: int = 30
    repo_rate_pct: float = 5.0


@router.post("/desk/repo", dependencies=[Depends(RequireFeature("access_desk_repo"))])
async def api_repo(req: RepoRequest):
    return await DeskService.repo(
        bond_id=req.bond_id,
        notional=req.notional,
        tenor_days=req.tenor_days,
        repo_rate_pct=req.repo_rate_pct,
    )


@router.get("/desk/stress", dependencies=[Depends(RequireFeature("access_desk_stress"))])
async def api_stress():
    return await DeskService.stress()


@router.get("/desk/curve", dependencies=[Depends(RequireFeature("access_desk_curve"))])
async def api_curve():
    return await DeskService.curve()


@router.get("/desk/spreads", dependencies=[Depends(RequireFeature("access_desk_rv"))])
async def api_desk_spreads():
    return await DeskService.spreads()


@router.get("/desk/status", dependencies=[Depends(RequireFeature("access_desk_rv"))])
async def api_desk_status():
    return await DeskService.status()
