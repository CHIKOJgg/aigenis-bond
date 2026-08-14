"""Server-side diagnostics for live bond rows.

Run this on a host that can reach the production PostgreSQL database:

    python scripts/verify_live_db.py [--asof YYYY-MM-DD] [--strict 0.5] [--json]

Flags every bond whose ``yield_to_maturity`` or core fields disagree with the
engine's recomputation or violate ingestion guards. The check mirrors what
``api/demo._bond_analytics`` would compute for the same row, plus the sanity
filters applied during ingestion (``scraper.validation``).

Because the database is unreachable from the typical dev box (DNS error
``getaddrinfo failed``), this script is intended to be run on the server where
``DATABASE_URL`` is resolvable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime

from sqlalchemy import select

from desk.ytm import to_price_pct, ytm_from_price
from scraper.config import get_settings
from scraper.db import dispose, get_session_factory
from scraper.orm import BondORM

PRICE_PCT_MIN = 0.5
PRICE_PCT_MAX = 500.0


def _row(b: BondORM) -> dict:
    return {
        "internal_id": b.internal_id,
        "name": b.name,
        "currency": b.currency,
        "market": getattr(b, "market", None) or "bcse",
        "status": b.status,
        "issuer": b.issuer,
        "maturity_date": b.maturity_date.isoformat() if b.maturity_date else None,
        "coupon_rate": float(b.coupon_rate) if b.coupon_rate is not None else None,
        "coupon_frequency": b.coupon_frequency,
        "nominal": float(b.nominal) if b.nominal is not None else None,
        "price": float(b.price) if b.price is not None else None,
        "yield_to_maturity": float(b.yield_to_maturity) if b.yield_to_maturity is not None else None,
    }


def _check(row: dict, asof: date, tol: float) -> list[dict]:
    issues: list[dict] = []
    price_pct = to_price_pct(row["price"], row["nominal"])
    stored = row["yield_to_maturity"]
    if stored is None or stored <= 0:
        issues.append({"field": "yield_to_maturity", "issue": "missing_or_nonpositive", "value": stored})

    if row["coupon_rate"] is None or row["coupon_rate"] <= 0:
        issues.append({"field": "coupon_rate", "issue": "missing_or_nonpositive", "value": row["coupon_rate"]})

    if price_pct is None:
        issues.append({"field": "price", "issue": "missing_or_nonpositive", "value": row["price"]})
    elif not (PRICE_PCT_MIN <= price_pct <= PRICE_PCT_MAX):
        issues.append({
            "field": "price_pct", "issue": "outside_sane_range",
            "value": round(price_pct, 4),
            "range": [PRICE_PCT_MIN, PRICE_PCT_MAX],
        })

    mat: date | None = None
    if row["maturity_date"] is None:
        issues.append({"field": "maturity_date", "issue": "missing", "value": None})
    else:
        try:
            mat = date.fromisoformat(row["maturity_date"])
        except ValueError:
            issues.append({"field": "maturity_date", "issue": "unparseable", "value": row["maturity_date"]})
            mat = None
        if mat is not None and mat <= asof:
            issues.append({"field": "maturity_date", "issue": "matured_or_today", "value": mat.isoformat()})

    if (
        price_pct is not None
        and row["coupon_rate"] is not None
        and row["coupon_rate"] > 0
        and mat is not None
        and mat > asof
    ):
        rec = ytm_from_price(
            price_pct=price_pct,
            coupon_rate_pct=float(row["coupon_rate"]),
            coupon_frequency=int(row["coupon_frequency"] or 2),
            maturity=mat,
            asof=asof,
        )
        if stored is not None and stored > 0 and rec is not None:
            diff = stored - rec
            if abs(diff) > tol:
                issues.append({
                    "field": "yield_to_maturity",
                    "issue": "diverges_from_price_recompute",
                    "stored": round(stored, 4),
                    "recomputed": round(rec, 4),
                    "diff_pp": round(diff, 2),
                })
    return issues


async def run(asof: date, tol: float, as_json: bool) -> int:
    get_settings()
    factory = get_session_factory()
    counts = {"total": 0, "with_issues": 0, "by_issue": {}}
    flagged: list[dict] = []
    db_error: str | None = None
    rows: list[BondORM] = []

    try:
        async with factory() as session:
            rows = list((await session.execute(select(BondORM))).scalars().all())
    except Exception as exc:  # pragma: no cover — DB unreachable / auth / network
        db_error = f"{type(exc).__name__}: {exc}"
        await dispose()

    for bond in rows:
        counts["total"] += 1
        row = _row(bond)
        issues = _check(row, asof, tol)
        if issues:
            counts["with_issues"] += 1
            flagged.append({"internal_id": row["internal_id"], "issues": issues})
            for it in issues:
                key = it["issue"]
                counts["by_issue"][key] = counts["by_issue"].get(key, 0) + 1

    report = {
        "as_of": asof.isoformat(),
        "timestamp": datetime.now(UTC).isoformat(),
        "tolerance_pp": tol,
        "db_status": "ok" if db_error is None else "unreachable",
        "db_error": db_error,
        "summary": counts,
        "flagged": flagged,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2) if as_json else _render_text(report))
    if db_error is not None:
        await dispose()
        return 2
    await dispose()
    return 1 if counts["with_issues"] > 0 else 0


def _render_text(report: dict) -> str:
    out = [
        f"DB bond audit {report['as_of']} (tol +/- {report['tolerance_pp']}pp, {report['timestamp']})",
        f"  db_status: {report.get('db_status', 'ok')}",
    ]
    if report.get("db_error"):
        out.append(f"  db_error: {report['db_error']}")
    out += [
        f"  total: {report['summary']['total']}",
        f"  with_issues: {report['summary']['with_issues']}",
        "  by_issue:",
    ]
    for k, v in report["summary"]["by_issue"].items():
        out.append(f"    {k}: {v}")
    if report["flagged"]:
        out.append("  flagged:")
        for item in report["flagged"]:
            for it in item["issues"]:
                extras = {kk: vv for kk, vv in it.items() if kk not in {"field", "issue"}}
                out.append(f"    {item['internal_id']}: {it['field']}={it['issue']} {extras}")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--strict", type=float, default=0.5,
                        help="flag stored-vs-recomputed YTM deviations above N pp")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    asof = date.fromisoformat(args.asof)
    return asyncio.run(run(asof, args.strict, args.json))


if __name__ == "__main__":
    sys.exit(main())
