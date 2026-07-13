"""Команды V4: desk — yield curve, RV, duration, carry, repo, stress (async)."""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import select

from desk import carry, duration, relative_value, repo, stress, yield_curve
from desk.repository import (
    latest_rv_signals,
    latest_stress_runs,
    save_carry_trades,
    save_curve_points,
    save_repo_deal,
    save_rv_signals,
    save_stress_run,
)
from scraper.db import session_scope
from scraper.models import Bond
from scraper.orm import BondORM


async def _fetch_bonds() -> list[Bond]:
    async with session_scope() as session:
        res = await session.execute(select(BondORM))
        orm_bonds = list(res.scalars().all())
        return [
            Bond(
                internal_id=b.internal_id,
                name=b.name,
                currency=b.currency,
                yield_to_maturity=b.yield_to_maturity,
                coupon_rate=b.coupon_rate,
                coupon_frequency=b.coupon_frequency,
                maturity_date=b.maturity_date,
                price=b.price,
                issuer=b.issuer,
                status=b.status,
                nominal=b.nominal,
                fetched_at=b.fetched_at,
            )
            for b in orm_bonds
        ]


async def cmd_desk_curve() -> int:
    bonds = await _fetch_bonds()
    by_currency: dict[str, list[Bond]] = {}
    for b in bonds:
        by_currency.setdefault(b.currency, []).append(b)

    out: dict = {}
    async with session_scope() as session:
        for currency, bs in by_currency.items():
            curve = yield_curve.curve_from_bonds(bs)
            if not curve.points:
                continue
            params = yield_curve.fit_nelson_siegel(curve.points)
            await save_curve_points(
                session,
                currency=currency,
                points=[(p.tenor, p.years, p.rate_pct) for p in curve.points],
                ns_params=params.model_dump(),
            )
            out[currency] = {
                "slope": round(curve.slope(), 4),
                "points": [(p.tenor, p.rate_pct) for p in curve.points],
                "nelson_siegel": params.model_dump(),
            }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


async def cmd_desk_rv() -> int:
    bonds = await _fetch_bonds()
    signals = relative_value.relative_value_signals(bonds)
    buy_signals = [s for s in signals if s.side == "buy"][:10]
    sell_signals = [s for s in signals if s.side == "sell"][:10]

    async with session_scope() as session:
        await save_rv_signals(session, signals)

    out = {
        "buy": [
            {
                "id": s.internal_id,
                "z": s.z_score,
                "spread_pct": s.spread_pct,
                "rationale": s.rationale,
            }
            for s in buy_signals
        ],
        "sell": [
            {
                "id": s.internal_id,
                "z": s.z_score,
                "spread_pct": s.spread_pct,
                "rationale": s.rationale,
            }
            for s in sell_signals
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


async def cmd_desk_duration(internal_id: str | None = None) -> int:
    bonds = await _fetch_bonds()
    if internal_id:
        bond = next((b for b in bonds if b.internal_id == internal_id), None)
        if bond is None:
            print(f"Bond {internal_id} not found")
            return 1
        report = duration.duration_report(bond)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        weights = {b.internal_id: 1 / len(bonds) for b in bonds} if bonds else {}
        report = duration.portfolio_duration(bonds, weights=weights)
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


async def cmd_desk_carry(funding_rate: float = 5.0) -> int:
    bonds = await _fetch_bonds()
    trades = carry.rank_carry(bonds, funding_rate_pct=funding_rate)
    top = trades[:20]

    async with session_scope() as session:
        await save_carry_trades(session, trades)

    print(
        json.dumps(
            [
                {
                    "id": t.internal_id,
                    "coupon": t.coupon_pct,
                    "funding": t.funding_rate_pct,
                    "rolldown_bps": t.rolldown_bps,
                    "expected_pnl_pct": t.expected_pnl_pct,
                }
                for t in top
            ],
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


async def cmd_desk_repo(internal_id: str, notional: float = 1000.0, tenor_days: int = 30) -> int:
    bonds = await _fetch_bonds()
    bond = next((b for b in bonds if b.internal_id == internal_id), None)
    if bond is None:
        print(f"Bond {internal_id} not found")
        return 1
    haircut = repo.haircut_by_issuer(bond.issuer)
    deal = repo.repo_deal(
        bond,
        notional=Decimal(str(notional)),
        haircut_pct=haircut,
        repo_rate_pct=5.0,
        tenor_days=tenor_days,
    )

    async with session_scope() as session:
        await save_repo_deal(session, deal)

    print(json.dumps(deal.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


async def cmd_desk_stress() -> int:
    bonds = await _fetch_bonds()
    weights = {b.internal_id: Decimal("1000") for b in bonds}
    results: dict = {}
    async with session_scope() as session:
        for name, scn in stress.PRESET_SCENARIOS.items():
            res = stress.run_stress(scn, [(b, weights[b.internal_id]) for b in bonds])
            await save_stress_run(session, res)
            results[name] = {
                "pnl_pct": res.pnl_pct,
                "pnl": float(res.pnl),
                "stressed_value": float(res.stressed_value),
            }
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


async def cmd_desk_status() -> int:
    async with session_scope() as session:
        rv = await latest_rv_signals(session, limit=5)
        stress_runs = await latest_stress_runs(session, limit=5)
    out = {
        "rv_top": [{"id": s.internal_id, "z": float(s.z_score), "side": s.side} for s in rv],
        "stress_recent": [
            {
                "name": s.scenario_name,
                "pnl_pct": float(s.pnl_pct),
                "asof": s.asof_date.isoformat(),
            }
            for s in stress_runs
        ],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


async def cmd_alerts_check() -> int:
    from notifications.alerts_service import run_alert_checks

    fired = await run_alert_checks()
    print(json.dumps({"fired_alerts": fired}, ensure_ascii=False, indent=2))
    return 0
