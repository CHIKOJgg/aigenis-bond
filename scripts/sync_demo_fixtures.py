"""Synchronize demo fixtures with the production scoring engine.

Reproducible regeneration of the demo snapshot (demo-data/v1 + the identical
frontend copy) so every number the demo shows is what the engine itself
produces for those bonds:

* stored ``yield_to_maturity`` is brought in line with the engine's
  ``ytm_from_price`` (price/coupon/maturity) when it deviates by > 0.5pp;
* ``scores.json`` is regenerated with ``score_bond`` (same inputs as
  ``api.demo._bond_analytics``);
* ``explanations.json`` is regenerated from ``scoring.explain``;
* ``market_summary.json`` tier counts are recomputed from the new scores.

Run: python scripts/sync_demo_fixtures.py [--asof YYYY-MM-DD] [--write]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from desk.ytm import to_price_pct, ytm_from_price
from scoring.engine import score_bond
from scoring.explain import explain_score

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo-data" / "v1"
FRONTEND_DIR = ROOT / "frontend" / "src" / "demo" / "data"

TIER_STATUS = {
    "S": "attractive",
    "A": "attractive",
    "B": "neutral",
    "C": "review",
    "D": "high_risk",
}

FILES = (
    "bonds_bcse.json",
    "bonds_moex.json",
    "scores.json",
    "market_summary.json",
    "explanations.json",
)

YTM_TOLERANCE_PP = 0.5


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _bonds() -> list[dict]:
    return _load(DEMO_DIR / "bonds_bcse.json") + _load(DEMO_DIR / "bonds_moex.json")


def fix_ytm(asof: date) -> tuple[list[dict], list[str]]:
    changes: list[str] = []
    bonds = _bonds()
    for b in bonds:
        price_pct = to_price_pct(b.get("price"), b.get("nominal"))
        maturity = b.get("maturity_date")
        coupon = b.get("coupon_rate")
        stored = b.get("yield_to_maturity")
        rec: float | None = None
        if price_pct is not None and coupon is not None and maturity:
            rec = ytm_from_price(
                price_pct=price_pct,
                coupon_rate_pct=float(coupon),
                coupon_frequency=int(b.get("coupon_frequency") or 2),
                maturity=date.fromisoformat(maturity),
                asof=asof,
            )
        stored_f = float(stored) if stored is not None else None
        if stored_f is not None and rec is not None and abs(stored_f - rec) > YTM_TOLERANCE_PP:
            changes.append(
                f"{b['internal_id']}: ytm {stored_f} -> {round(rec, 2)} (diff {stored_f - rec:+.2f}pp)"
            )
            b["yield_to_maturity"] = round(rec, 2)
        elif stored_f is None and rec is not None:
            changes.append(f"{b['internal_id']}: ytm None -> {round(rec, 2)}")
            b["yield_to_maturity"] = round(rec, 2)
        elif rec is None:
            changes.append(
                f"{b['internal_id']}: cannot recompute ytm (missing price/coupon/maturity)"
            )
    return bonds, changes


def _score_inputs(b: dict, ytm):
    return {
        "internal_id": b["internal_id"],
        "yield_to_maturity": ytm,
        "currency": b.get("currency") or "",
        "maturity_date": date.fromisoformat(b["maturity_date"]) if b.get("maturity_date") else None,
        "status": str(b.get("status") or "active"),
        "issuer": b.get("issuer"),
        "price": to_price_pct(b.get("price"), b.get("nominal")),
        "nominal": Decimal("100"),
        "coupon_rate": float(b["coupon_rate"]) if b.get("coupon_rate") is not None else None,
        "market": str(b.get("market") or "bcse"),
    }


def regenerate_scores(bonds: list[dict]) -> list[dict]:
    scores: list[dict] = []
    for b in bonds:
        bs = score_bond(**_score_inputs(b, b.get("yield_to_maturity")))
        scores.append(
            {
                "internal_id": b["internal_id"],
                "score": round(bs.score, 2),
                "tier": bs.tier,
                "status": TIER_STATUS.get(bs.tier, "no_data"),
                "computed_at": b.get("fetched_at") or datetime.now(UTC).isoformat(),
                "breakdown": bs.breakdown.model_dump(),
            }
        )
    return sorted(scores, key=lambda x: x["internal_id"])


def regenerate_explanations(bonds: list[dict]) -> list[dict]:
    explanations: list[dict] = []
    for b in bonds:
        ytm = b.get("yield_to_maturity")
        coupon = b.get("coupon_rate")
        bs = score_bond(**_score_inputs(b, ytm))
        expl = explain_score(
            bs,
            currency=b.get("currency") or "",
            ytm_pct=float(ytm) if ytm is not None else None,
            coupon_pct=float(coupon) if coupon is not None else None,
        )
        explanations.append(
            {
                "internal_id": b["internal_id"],
                "status": TIER_STATUS.get(bs.tier, "no_data"),
                "verdict": expl.verdict,
                "summary": expl.summary,
                "factors": [
                    {
                        "label": f.label,
                        "direction": f.impact,
                        "plainText": f.detail,
                        "importance": "high"
                        if abs(f.points) >= 5.0
                        else "medium"
                        if abs(f.points) >= 2.0
                        else "low",
                    }
                    for f in expl.factors
                ],
                "strengths": expl.strengths,
                "weaknesses": expl.weaknesses,
            }
        )
    return sorted(explanations, key=lambda x: x["internal_id"])


def regenerate_market_summary(bonds: list[dict], scores: list[dict]) -> dict:
    score_by_id = {s["internal_id"]: s for s in scores}
    markets: dict[str, dict] = {}
    for b in bonds:
        mkey = "moex" if b.get("market") == "moex" else "bcse"
        stats = markets.setdefault(
            mkey,
            {
                "total_bonds": 0,
                "attractive_ideas": 0,
                "needs_review": 0,
                "neutral": 0,
                "high_risk": 0,
                "best_yield_pct": None,
                "best_yield_id": None,
                "source": "demo snapshot",
            },
        )
        stats["total_bonds"] += 1
        status = score_by_id.get(b["internal_id"], {}).get("status", "no_data")
        if status == "attractive":
            stats["attractive_ideas"] += 1
        elif status == "neutral":
            stats["neutral"] += 1
        elif status == "review":
            stats["needs_review"] += 1
        elif status == "high_risk":
            stats["high_risk"] += 1
        ytm = b.get("yield_to_maturity")
        if ytm is not None and (stats["best_yield_pct"] is None or ytm > stats["best_yield_pct"]):
            stats["best_yield_pct"] = ytm
            stats["best_yield_id"] = b["internal_id"]

    bcse = markets["bcse"]
    moex = markets["moex"]
    snapshot_time = bonds[0].get("fetched_at") if bonds else datetime.now(UTC).isoformat()
    best_global = (
        bcse["best_yield_pct"]
        if bcse["best_yield_pct"] is not None
        and (moex["best_yield_pct"] is None or bcse["best_yield_pct"] >= moex["best_yield_pct"])
        else moex["best_yield_pct"]
    )
    return {
        "as_of": snapshot_time,
        "markets": {"bcse": bcse, "moex": moex},
        "global": {
            "attractive_ideas": bcse["attractive_ideas"] + moex["attractive_ideas"],
            "needs_review": bcse["needs_review"] + moex["needs_review"],
            "best_yield_pct": best_global,
            "data_status": "ok",
            "updated_at": snapshot_time,
        },
    }


def check_portfolio_benchmarks(bonds: list[dict]) -> None:
    templates = _load(DEMO_DIR / "portfolio_templates.json")
    by_id = {b["internal_id"]: b for b in bonds}
    for template in templates.values():
        positions = template.get("positions", [])
        if not positions:
            continue
        invested = sum(float(p["weight_pct"]) for p in positions)
        if invested <= 0:
            continue
        ytm_w = (
            sum(
                float(by_id[p["instrument_id"]]["yield_to_maturity"]) * float(p["weight_pct"])
                for p in positions
                if p["instrument_id"] in by_id
                and by_id[p["instrument_id"]].get("yield_to_maturity")
            )
            / invested
        )
        bench = template.get("benchmarks", {})
        print(
            f"portfolio {template['id']}: weighted_yield={ytm_w:.2f}% "
            f"vs benchmark={bench.get('expected_yield_pct')}% "
            f"(delta {ytm_w - float(bench.get('expected_yield_pct', 0)):+.2f}pp)"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asof", default=str(date.today()))
    parser.add_argument("--write", action="store_true", help="write fixed files (default: dry run)")
    args = parser.parse_args()
    asof = date.fromisoformat(args.asof)

    bonds, changes = fix_ytm(asof)
    print(f"YTM as of {asof.isoformat()}: {len(changes)} change(s)")
    for line in changes:
        print(f"  {line}")

    scores = regenerate_scores(bonds)
    explanations = regenerate_explanations(bonds)
    summary = regenerate_market_summary(bonds, scores)

    print("\nRegenerated scores:")
    for s in scores:
        print(f"  {s['internal_id']}: score={s['score']} tier={s['tier']} status={s['status']}")
    print("\nMarket summary:")
    for mkey, stats in summary["markets"].items():
        print(
            f"  {mkey}: total={stats['total_bonds']} attractive={stats['attractive_ideas']} "
            f"neutral={stats['neutral']} review={stats['needs_review']} "
            f"high_risk={stats['high_risk']} best_yield={stats['best_yield_pct']} ({stats['best_yield_id']})"
        )
    check_portfolio_benchmarks(bonds)

    if not args.write:
        print("\nDry run -- no files written. Re-run with --write to apply.")
        return 0

    _dump(DEMO_DIR / "bonds_bcse.json", [b for b in bonds if b.get("market") != "moex"])
    _dump(DEMO_DIR / "bonds_moex.json", [b for b in bonds if b.get("market") == "moex"])
    _dump(DEMO_DIR / "scores.json", scores)
    _dump(DEMO_DIR / "market_summary.json", summary)
    _dump(DEMO_DIR / "explanations.json", explanations)
    for name in FILES:
        src = DEMO_DIR / name
        dst = FRONTEND_DIR / name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"synced {dst.relative_to(ROOT)}")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
