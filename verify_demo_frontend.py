"""Replicate the demo frontend runPortfolioOptimizer against the FIXED demo
data to verify strategy expected-return monotonicity (passive < aggressive)."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent
BCSE = json.loads((REPO / "demo-data/v1/bonds_bcse.json").read_text(encoding="utf-8"))
SCORES = json.loads((REPO / "demo-data/v1/scores.json").read_text(encoding="utf-8"))
score_map = {s["internal_id"]: s for s in SCORES}

PROFILES = {
    "Conservative": {"baseReturn": 9.5},
    "Balanced": {"baseReturn": 12.4},
    "Carry Trade": {"baseReturn": 13.5},
    "Metals++": {"baseReturn": 11.5},
    "Dollarization": {"baseReturn": 11.0},
    "Aggressive": {"baseReturn": 15.0},
    "Maximum Reward/Risk": {"baseReturn": 16.5},
}

STRATEGY_WEIGHTS = {
    "Conservative": {"score": 0.15, "yield": 0.05, "safety": 0.8},
    "Balanced": {"score": 0.4, "yield": 0.15, "safety": 0.45},
    "Aggressive": {"score": 0.15, "yield": 0.85, "safety": 0.0},
    "Carry Trade": {"score": 0.3, "yield": 0.6, "safety": 0.1},
    "Dollarization": {"score": 0.3, "yield": 0.2, "safety": 0.5},
    "Maximum Reward/Risk": {"score": 1.0, "yield": 0.0, "safety": 0.0},
    "Metals++": {"score": 0.3, "yield": 0.1, "safety": 0.6},
}


def honest_ytm(b):
    idx = (b.get("indexation_currency") or "").upper()
    cp = b.get("coupon_rate")
    if idx in ("XAU", "XAG", "XPT", "GOLD", "SILVER", "PLATINUM") and (cp is None or cp <= 0.01):
        return 0
    return b.get("yield_to_maturity")


def days_to_mat(b):
    if b.get("term_days") is not None:
        return b["term_days"]
    return None


def strategy_rank_score(b, strategy):
    sc = score_map.get(b["internal_id"], {})
    if strategy == "Maximum Reward/Risk":
        eff = (sc.get("breakdown") or {}).get("efficiency_ratio")
        return eff * 6 if eff is not None else (sc.get("score") or 50)
    w = STRATEGY_WEIGHTS[strategy] or STRATEGY_WEIGHTS["Balanced"]
    bd = sc.get("breakdown") or {}
    score_val = sc.get("score") or 50
    yld = bd.get("yield_component") or honest_ytm(b) or 0
    safety = max((bd.get("credit_risk_component") or 30) + (bd.get("duration_component") or 0) / 4, 0)
    weighted = w["score"] * score_val + w["yield"] * yld + w["safety"] * safety
    if strategy == "Conservative":
        d = days_to_mat(b)
        if d is not None:
            if d > 5 * 365:
                weighted -= 12
            elif d <= 2 * 365:
                weighted += 8
        if b.get("is_government"):
            weighted += 8
        if b.get("price") is not None and b["price"] < 95:
            weighted -= 5
    elif strategy == "Aggressive":
        y = honest_ytm(b)
        if y is not None:
            weighted += min(y * 0.25, 10)
        if b.get("coupon_rate") is not None and b["coupon_rate"] > 0:
            weighted += min(b["coupon_rate"] * 0.15, 6)
        d = days_to_mat(b)
        if d is not None:
            if d < 365:
                weighted -= 10
            elif d > 8 * 365:
                weighted += 6
    return max(weighted, 0)


def run(capital=50000, strategy="Balanced", currency="BYN", top_n=8, market="BCSE"):
    allb = [b for b in BCSE if b.get("market", "bcse").upper() == market.upper()]
    if strategy == "Dollarization":
        usd = [b for b in allb if b.get("currency", "").upper() == "USD"
               or (b.get("indexation_currency") or "").upper() == "USD"]
        allb = usd or [b for b in allb if b.get("currency", "").upper() == currency.upper()]
    elif strategy == "Metals++":
        met = [b for b in allb if (b.get("indexation_currency") or "").upper() in ("XAU", "XAG", "XPT", "GOLD", "SILVER", "PLATINUM")
               or "айгенис" in (b.get("issuer") or "").lower()]
        allb = met
    else:
        allb = [b for b in allb if b.get("currency", "").upper() == currency.upper()]

    ranked = sorted(allb, key=lambda b: strategy_rank_score(b, strategy), reverse=True)
    selected = ranked[:top_n]
    if not selected or capital <= 0:
        return 0.0, []
    # allocation by score
    scores = [strategy_rank_score(b, strategy) for b in selected]
    total = sum(scores) or 1
    weighted_ytm = 0.0
    wsum = 0.0
    for b, s in zip(selected, scores):
        share = s / total
        y = honest_ytm(b)
        if y is not None and y >= 0:
            weighted_ytm += y * share
            wsum += share
    if wsum > 0:
        weighted_ytm /= wsum
    prof = PROFILES[strategy]
    correction = max(-2.5, min(2.5, (weighted_ytm or prof["baseReturn"]) - 12.4))
    expected = prof["baseReturn"] + correction
    return round(expected, 2), [b["internal_id"] for b in selected]


print("== Demo frontend optimizer (BCSE, BYN, capital 50000) ==")
order = ["Conservative", "Dollarization", "Metals++", "Balanced",
         "Carry Trade", "Aggressive", "Maximum Reward/Risk"]
results = {}
for s in order:
    er, sel = run(strategy=s)
    results[s] = er
    print(f"  {s:20} expected_return={er:6.2f}%  top={sel[:4]}")

print("\n== Monotonicity (passive < aggressive, full ordering) ==")
vals = [results[s] for s in order]
mono = all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
print("  strict ascending:", mono, vals)
# canonical pair
print("  Aggressive > Conservative:", results["Aggressive"] > results["Conservative"])
print("  all aggressive-family >= Conservative:",
      all(results[s] >= results["Conservative"]
          for s in ["Aggressive", "Carry Trade", "Maximum Reward/Risk", "Balanced", "Metals++", "Dollarization"]))
print("\n" + ("DEMO STRATEGY CHECKS PASSED" if (mono and results['Aggressive'] > results['Conservative']) else "FAILED"))
