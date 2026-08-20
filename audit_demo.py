"""Audit & regenerate the demo fixture data so it is internally consistent.

Resolves the stuck git merge conflicts in demo JSON, dedupes scores,
recomputes accrued interest from desk.cashflow, derives market_summary from
the (deduped) scores, aligns explanations statuses, and fixes the portfolio
benchmark duration.

Run from repo root:
    .venv/Scripts/python.exe audit_demo.py
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from desk.cashflow import accrued_interest
from desk.duration import duration_report

REPO = Path(__file__).resolve().parent
DATA_DIRS = [
    REPO / "demo-data" / "v1",
    REPO / "frontend" / "src" / "demo" / "data",
]

STATUS_FROM_TIER = {
    "S": "attractive",
    "A": "attractive",
    "B": "neutral",
    "C": "review",
    "D": "high_risk",
}
VERDICT_FROM_STATUS = {
    "attractive": "Привлекательная",
    "neutral": "Умеренно интересна",
    "review": "Средняя",
    "high_risk": "Слабая / избегать",
}


def resolve_conflicts(text: str, keep: str = "stashed") -> str:
    """Pick one side of every `<<<<<<< ... ======= ... >>>>>>>` block."""
    pat = re.compile(r"<<<<<<< .*?\n(.*?)=======\n(.*?)>>>>>>> .*?\n", re.DOTALL)

    def repl(m: re.Match) -> str:
        return m.group(2) if keep == "stashed" else m.group(1)

    return pat.sub(repl, text)


def load_resolved(path: Path, keep: str = "stashed"):
    return json.loads(resolve_conflicts(path.read_text(encoding="utf-8"), keep=keep))


def parse_date(s):
    if not s:
        return None
    return date.fromisoformat(s[:10])


def recompute_accrued(bond: dict) -> float:
    asof = parse_date(bond.get("fetched_at")) or date(2026, 8, 6)
    issue = parse_date(bond.get("start_date"))
    maturity = parse_date(bond.get("maturity_date"))
    coupon = bond.get("coupon_rate")
    freq = bond.get("coupon_frequency") or 2
    if coupon is None or issue is None or maturity is None:
        return 0.0
    return round(
        accrued_interest(
            coupon_rate_pct=float(coupon),
            coupon_frequency=int(freq),
            issue_date=issue,
            maturity_date=maturity,
            asof=asof,
        ),
        4,
    )


def process(data_dir: Path) -> None:  # noqa: C901
    print(f"\n=== {data_dir} ===")
    bcse = load_resolved(data_dir / "bonds_bcse.json", keep="upstream")
    moex = load_resolved(data_dir / "bonds_moex.json", keep="upstream")

    # ---- bonds: recompute accrued interest ----
    for arr in (bcse, moex):
        for b in arr:
            prev = b.get("accrued_interest")
            new = recompute_accrued(b)
            if prev is not None and abs(prev - new) > 0.01:
                print(f"  [accrued] {b['internal_id']}: stored={prev} recomputed={new}")
            b["accrued_interest"] = new

    (data_dir / "bonds_bcse.json").write_text(
        json.dumps(bcse, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (data_dir / "bonds_moex.json").write_text(
        json.dumps(moex, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  bonds: {len(bcse)} bcse / {len(moex)} moex written")

    all_bonds = {b["internal_id"]: b for b in bcse + moex}

    # ---- scores: resolve + dedupe (keep first occurrence) ----
    scores = load_resolved(data_dir / "scores.json", keep="stashed")
    seen = {}
    deduped = []
    for s in scores:
        iid = s["internal_id"]
        if iid in seen:
            print(f"  [dedupe] dropped duplicate {iid}")
            continue
        seen[iid] = True
        deduped.append(s)
    print(f"  scores: {len(scores)} -> {len(deduped)} unique")

    # sanity: score == reward - risk (where both present)
    for s in deduped:
        bd = s.get("breakdown", {})
        if "reward_subtotal" in bd and "risk_subtotal" in bd:
            expected = round(bd["reward_subtotal"] - bd["risk_subtotal"], 2)
            if abs(expected - s["score"]) > 0.05:
                print(f"  [WARN] {s['internal_id']} score {s['score']} != reward-risk {expected}")

    (data_dir / "scores.json").write_text(
        json.dumps(deduped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # ---- market_summary: derive from scores + bonds ----
    status_of = {s["internal_id"]: s["status"] for s in deduped}

    def summarise(market_bonds):
        counts = {"attractive_ideas": 0, "needs_review": 0, "neutral": 0, "high_risk": 0}
        best = {"ytm": -1.0, "id": None}
        for b in market_bonds:
            st = status_of.get(b["internal_id"])
            if st in ("attractive",):
                counts["attractive_ideas"] += 1
            elif st == "review":
                counts["needs_review"] += 1
            elif st == "neutral":
                counts["neutral"] += 1
            elif st == "high_risk":
                counts["high_risk"] += 1
            ytm = float(b.get("yield_to_maturity") or 0.0)
            if ytm > best["ytm"]:
                best = {"ytm": ytm, "id": b["internal_id"]}
        return counts, best

    bcse_counts, bcse_best = summarise(bcse)
    moex_counts, moex_best = summarise(moex)

    global_attractive = bcse_counts["attractive_ideas"] + moex_counts["attractive_ideas"]
    global_review = bcse_counts["needs_review"] + moex_counts["needs_review"]

    summary = {
        "as_of": "2026-08-06T09:42:00+03:00",
        "markets": {
            "bcse": {
                "total_bonds": len(bcse),
                **bcse_counts,
                "best_yield_pct": bcse_best["ytm"],
                "best_yield_id": bcse_best["id"],
                "source": "demo snapshot",
            },
            "moex": {
                "total_bonds": len(moex),
                **moex_counts,
                "best_yield_pct": moex_best["ytm"],
                "best_yield_id": moex_best["id"],
                "source": "demo snapshot",
            },
        },
        "global": {
            "attractive_ideas": global_attractive,
            "needs_review": global_review,
            "best_yield_pct": max(bcse_best["ytm"], moex_best["ytm"]),
            "data_status": "ok",
            "updated_at": "2026-08-06T09:42:00+03:00",
        },
    }
    (data_dir / "market_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  market_summary bcse={bcse_counts} moex={moex_counts}")

    # ---- explanations: align status + verdict to scores ----
    expl_path = data_dir / "explanations.json"
    if expl_path.exists():
        expl = load_resolved(expl_path, keep="stashed")
        n = 0
        for e in expl:
            iid = e["internal_id"]
            st = status_of.get(iid)
            if st and e.get("status") != st:
                print(f"  [explain] {iid}: status {e.get('status')} -> {st}")
                e["status"] = st
                n += 1
            if st and e.get("verdict") != VERDICT_FROM_STATUS.get(st):
                e["verdict"] = VERDICT_FROM_STATUS.get(st, e.get("verdict"))
        (expl_path).write_text(
            json.dumps(expl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  explanations: {n} status updates")

    # ---- portfolio_templates: fix benchmark duration ----
    # The benchmark ``duration_years`` is the portfolio's rate-risk measure and
    # MUST equal the cashflow-based modified duration the engine reports for the
    # same holdings — not a weighted time-to-maturity proxy, which systematically
    # overstates rate sensitivity for coupon-paying bonds. We recompute it here
    # from ``desk.duration`` so the Portfolio Impact "before" card agrees with
    # the per-bond duration the rest of the platform shows.
    pt_path = data_dir / "portfolio_templates.json"
    if pt_path.exists():
        pt = load_resolved(pt_path, keep="stashed")
        ref = parse_date(pt.get("as_of") or "2026-08-06") or date(2026, 8, 6)
        for key, tpl in pt.items():
            positions = tpl.get("positions", [])
            total = tpl.get("total_value_byn", 0)
            if not positions or not total:
                continue
            wsum = 0.0
            dur_acc = 0.0
            for p in positions:
                bid = p.get("instrument_id")
                bond = all_bonds.get(bid)
                if not bond:
                    continue
                w = p.get("value_byn", 0) / total
                maturity = parse_date(bond.get("maturity_date"))
                start = parse_date(bond.get("start_date"))
                if maturity is None or start is None:
                    continue

                class _B:
                    pass

                fb = _B()
                fb.internal_id = bid
                fb.maturity_date = maturity
                fb.yield_to_maturity = float(bond.get("yield_to_maturity") or 0.0)
                fb.coupon_rate = bond.get("coupon_rate")
                fb.coupon_frequency = bond.get("coupon_frequency") or 2
                fb.nominal = Decimal(str(bond.get("nominal") or 1000))
                fb.start_date = start
                rep = duration_report(fb, asof=ref)
                dur_acc += w * rep.modified_duration
                wsum += w
            if wsum > 0:
                new_dur = round(dur_acc / wsum, 1)
                old = tpl.get("benchmarks", {}).get("duration_years")
                if old is not None and abs(old - new_dur) > 0.05:
                    print(
                        f"  [portfolio] {key}: duration_years {old} -> {new_dur} "
                        f"(weighted modified duration of positions)"
                    )
                tpl.setdefault("benchmarks", {})["duration_years"] = new_dur
        (pt_path).write_text(json.dumps(pt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    for d in DATA_DIRS:
        if d.exists():
            process(d)
    print("\nDONE")
