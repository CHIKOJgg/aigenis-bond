"""Use-case layer for desk analytics (RV, duration, carry, repo, stress, curve, spreads)."""

from __future__ import annotations

from decimal import Decimal

from api.analytics._helpers import _all_bonds
from api.dto import analytics as dto
from desk import carry as desk_carry
from desk import duration as desk_duration
from desk import relative_value as desk_rv
from desk import repo as desk_repo
from desk import spreads as desk_spreads
from desk import stress as desk_stress
from desk import yield_curve as desk_curve
from desk.repository import (
    latest_rv_signals,
    latest_spread_reports,
    latest_stress_runs,
    save_spread_reports,
)
from scraper.db import session_scope


class DeskService:
    """Desk analytics use cases shared by the API routers."""

    @staticmethod
    async def rv() -> list[dto.RvSignal]:
        bonds = await _all_bonds()
        signals = desk_rv.relative_value_signals(bonds)
        return [
            dto.RvSignal(
                internal_id=s.internal_id,
                side=s.side,
                z_score=round(float(s.z_score), 3) if s.z_score is not None else None,
                spread_pct=round(float(s.spread_pct), 3) if s.spread_pct is not None else None,
            )
            for s in signals
        ]

    @staticmethod
    async def duration(bond_id: str | None) -> dto.DurationReport:
        from fastapi import HTTPException

        bonds = await _all_bonds()
        if bond_id:
            bond = next((b for b in bonds if b.internal_id == bond_id), None)
            if bond is None:
                raise HTTPException(status_code=404, detail=f"Bond {bond_id} not found")
            rep = desk_duration.duration_report(bond)
            title = f"duration:{bond.internal_id}"
        else:
            weights = {b.internal_id: Decimal("1") / Decimal(len(bonds) or 1) for b in bonds}
            rep = desk_duration.portfolio_duration(bonds, weights=weights)
            title = "duration:portfolio"
        return dto.DurationReport(
            title=title,
            macaulay_duration=round(float(rep.macaulay_duration), 4),
            modified_duration=round(float(rep.modified_duration), 4),
            convexity=round(float(rep.convexity), 4),
            dv01=round(float(rep.dv01), 5),
            key_rate_durations={k: round(float(v), 5) for k, v in rep.key_rate_durations.items()},
        )

    @staticmethod
    async def carry(funding_rate_pct: float) -> list[dto.CarryTrade]:
        bonds = await _all_bonds()
        trades = desk_carry.rank_carry(bonds, funding_rate_pct=funding_rate_pct)
        return [
            dto.CarryTrade(
                internal_id=t.internal_id,
                coupon_pct=round(float(t.coupon_pct), 3),
                rolldown_bps=round(float(t.rolldown_bps), 2),
                expected_pnl_pct=round(float(t.expected_pnl_pct), 4),
            )
            for t in trades
        ]

    @staticmethod
    async def repo(
        bond_id: str, notional: float, tenor_days: int, repo_rate_pct: float
    ) -> dto.RepoDeal:
        from fastapi import HTTPException

        bonds = await _all_bonds()
        bond = next((b for b in bonds if b.internal_id == bond_id), None)
        if bond is None:
            raise HTTPException(status_code=404, detail=f"Bond {bond_id} not found")
        haircut = desk_repo.haircut_by_issuer(bond.issuer)
        deal = desk_repo.repo_deal(
            bond,
            notional=Decimal(str(notional)),
            haircut_pct=haircut,
            repo_rate_pct=repo_rate_pct,
            tenor_days=tenor_days,
        )
        return dto.RepoDeal(
            internal_id=bond_id,
            collateral_value=float(deal.collateral_value),
            haircut_pct=float(deal.haircut_pct),
            cash_lent=float(deal.cash_lent),
            repo_rate_pct=float(deal.repo_rate_pct),
            tenor_days=deal.tenor_days,
            accrued_interest=float(deal.accrued_interest),
        )

    @staticmethod
    async def stress() -> list[dto.StressResult]:
        bonds = await _all_bonds()
        weights = {b.internal_id: Decimal("1000") for b in bonds}
        out: list[dto.StressResult] = []
        for name, scn in desk_stress.PRESET_SCENARIOS.items():
            res = desk_stress.run_stress(scn, [(b, weights[b.internal_id]) for b in bonds])
            out.append(
                dto.StressResult(
                    scenario=name,
                    kind=scn.kind,
                    pnl_pct=round(float(res.pnl_pct), 4),
                    pnl=round(float(res.pnl), 2),
                )
            )
        return out

    @staticmethod
    async def curve() -> list[dto.CurveReport]:
        bonds = await _all_bonds()
        by_cur: dict[str, list] = {}
        for b in bonds:
            by_cur.setdefault(str(b.currency), []).append(b)
        out: list[dto.CurveReport] = []
        for cur, bs in by_cur.items():
            curve = desk_curve.curve_from_bonds(bs)
            if not curve.points:
                continue
            params = desk_curve.fit_nelson_siegel(curve.points)
            out.append(
                dto.CurveReport(
                    currency=cur,
                    slope=round(float(curve.slope()), 4),
                    beta0=round(float(params.beta0), 4),
                    beta1=round(float(params.beta1), 4),
                    beta2=round(float(params.beta2), 4),
                    points=[
                        dto.CurvePoint(
                            tenor=p.tenor, years=p.years, rate_pct=round(float(p.rate_pct), 4)
                        )
                        for p in curve.points
                    ],
                )
            )
        return out

    @staticmethod
    async def spreads() -> list[dict]:
        """Z/G-spreads и сигнал mispricing (модельная цена vs рынок) по валютам."""
        bonds = await _all_bonds()
        by_cur: dict[str, list] = {}
        for b in bonds:
            by_cur.setdefault(str(b.currency), []).append(b)

        curves: dict[str, desk_curve.NelsonSiegelParams] = {}
        for cur, bs in by_cur.items():
            curve = desk_curve.curve_from_bonds(bs)
            if len(curve.points) >= 3:
                curves[cur] = desk_curve.fit_nelson_siegel(curve.points)

        reports = desk_spreads.compute_spreads(bonds, curves)
        if reports:
            async with session_scope() as session:
                await save_spread_reports(session, reports)
                await session.commit()

        return [r.model_dump() for r in reports[:100]]

    @staticmethod
    async def status() -> dto.DeskStatus:
        async with session_scope() as session:
            rv = await latest_rv_signals(session, limit=5)
            stress_runs = await latest_stress_runs(session, limit=3)
            spreads = await latest_spread_reports(session, limit=5)
        return dto.DeskStatus(
            rv=[
                {
                    "internal_id": s.internal_id,
                    "z_score": round(float(s.z_score), 3),
                    "side": s.side,
                }
                for s in rv
            ],
            stress=[
                {"scenario_name": r.scenario_name, "pnl_pct": round(float(r.pnl_pct), 4)}
                for r in stress_runs
            ],
            spreads=[
                {
                    "internal_id": s.internal_id,
                    "g_spread_pct": round(float(s.g_spread_pct), 4)
                    if s.g_spread_pct is not None
                    else None,
                    "side": s.side,
                }
                for s in spreads
            ],
        )
