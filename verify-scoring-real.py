"""Run production scoring + explanation against REAL bonds in the DB and verify
that strengths ("преимущества") and weaknesses ("недостатки") are generated.

Usage (inside the parser container, which has DATABASE_URL set):
    docker compose run --rm -v ${PWD}/verify-scoring-real.py:/app/verify-scoring-real.py \
        parser python3 verify-scoring-real.py [--limit N] [--market bcse|moex]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from desk.ytm import to_price_pct, ytm_from_price
from scraper.db import session_scope
from scraper.orm import BondORM


def _derive_ytm(bond: BondORM) -> float | None:
    if bond.yield_to_maturity is not None and float(bond.yield_to_maturity) > 0:
        return float(bond.yield_to_maturity)
    price_pct = to_price_pct(bond.price, bond.nominal)
    if price_pct is not None and bond.coupon_rate is not None and bond.maturity_date is not None:
        solved = ytm_from_price(
            price_pct=price_pct,
            coupon_rate_pct=float(bond.coupon_rate),
            coupon_frequency=int(bond.coupon_frequency or 2),
            maturity=bond.maturity_date,
            asof=date.today(),
        )
        if solved is not None and solved > 0:
            return round(solved, 4)
    return None


async def run(limit: int, market: str | None) -> int:
    from scoring.engine import score_bond
    from scoring.explain import explain_score

    async with session_scope() as session:
        stmt = (
            select(BondORM)
            .where(BondORM.status == "active")
            .order_by(BondORM.fetched_at.desc(), BondORM.name.asc())
            .limit(limit)
        )
        if market:
            stmt = select(BondORM).where(BondORM.status == "active", BondORM.market == market)
            stmt = stmt.order_by(BondORM.fetched_at.desc(), BondORM.name.asc()).limit(limit)
        bonds = list((await session.execute(stmt)).scalars().all())

    rows = []
    for b in bonds:
        ytm = _derive_ytm(b)
        price_pct = to_price_pct(b.price, b.nominal)
        if ytm is None and price_pct is None:
            continue
        bs = score_bond(
            internal_id=b.internal_id,
            yield_to_maturity=ytm,
            currency=b.currency,
            maturity_date=b.maturity_date,
            status=str(b.status or "active"),
            issuer=b.issuer,
            price=price_pct,
            nominal=Decimal("100"),
            coupon_rate=float(b.coupon_rate) if b.coupon_rate is not None else None,
            market=str(b.market or "bcse"),
        )
        expl = explain_score(
            bs,
            currency=b.currency,
            ytm_pct=ytm,
            coupon_pct=float(b.coupon_rate) if b.coupon_rate is not None else None,
        )
        rows.append(
            {
                "id": b.internal_id,
                "name": b.name,
                "currency": b.currency,
                "ytm": ytm,
                "score": bs.score,
                "tier": bs.tier,
                "strengths": expl.strengths,
                "weaknesses": expl.weaknesses,
                "verdict": expl.verdict,
                "summary": expl.summary,
            }
        )

    n = len(rows)
    n_scored = sum(1 for r in rows if r["score"] is not None)
    n_strengths = sum(1 for r in rows if r["strengths"])
    n_weaknesses = sum(1 for r in rows if r["weaknesses"])
    n_both = sum(1 for r in rows if r["strengths"] and r["weaknesses"])
    tiers: dict[str, int] = {}
    for r in rows:
        tiers[r["tier"]] = tiers.get(r["tier"], 0) + 1

    print("=" * 78)
    print(
        f"SCORING vs REAL DATA: {n} bonds scored from DB (market={market or 'all'}, limit={limit})"
    )
    print("=" * 78)
    print(f"  scored:               {n_scored}/{n}")
    print(f"  with strengths:       {n_strengths}  ({100 * n_strengths / max(n, 1):.0f}%)")
    print(f"  with weaknesses:      {n_weaknesses}  ({100 * n_weaknesses / max(n, 1):.0f}%)")
    print(f"  with BOTH:            {n_both}  ({100 * n_both / max(n, 1):.0f}%)")
    print(f"  tier distribution:    {tiers}")

    print("-" * 78)
    print("SAMPLES (top by score, middle, bottom):")
    ordered = sorted(rows, key=lambda r: r["score"] or -1, reverse=True)
    for label, idx in (("TOP", 0), ("MIDDLE", len(ordered) // 2), ("BOTTOM", -1)):
        r = ordered[idx]
        print(
            f"--- {label}: {r['id']} | {r['name'][:60]} | "
            f"score={r['score']:.2f} tier={r['tier']} ytm={r['ytm']}%"
        )
        print(f"    verdict: {r['verdict']}")
        print(f"    strengths  ({len(r['strengths'])}): " + " | ".join(r["strengths"]))
        print(f"    weaknesses ({len(r['weaknesses'])}): " + " | ".join(r["weaknesses"]))

    print("-" * 78)
    ok = n_scored > 0 and n_strengths > 0 and n_weaknesses > 0
    print(
        ("OK: " if ok else "FAIL: ") + "advantages (strengths) and disadvantages "
        "(weaknesses) are generated from real market data"
    )
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--market", choices=["bcse", "moex"], default=None)
    args = parser.parse_args()
    return asyncio.run(run(args.limit, args.market))


if __name__ == "__main__":
    sys.exit(main())
