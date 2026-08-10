from datetime import date
from decimal import Decimal

from scoring.engine import score_bond
from scoring.explain import explain_score

TIER_TO_STATUS = {
    "S": "attractive",
    "A": "attractive",
    "B": "neutral",
    "C": "review",
    "D": "high_risk",
}

bonds = [
    ("demo-bond-001", 12.5, 5.0, date(2030, 8, 7)),
    ("demo-bond-002", 8.0, 6.0, date(2029, 1, 15)),
    ("demo-bond-003", 5.5, 4.5, date(2027, 6, 10)),
]

print("scoring engine check (production score_bond v4 — same fn the API uses for the demo)")
print("-" * 70)
for iid, ytm, cp, mat in bonds:
    bs = score_bond(
        internal_id=iid,
        yield_to_maturity=ytm,
        currency="BYN",
        maturity_date=mat,
        status="active",
        issuer="DemoIssuer",
        price=Decimal("100"),
        nominal=Decimal("100"),
        coupon_rate=cp,
        market="bcse",
    )
    expl = explain_score(bs, currency="BYN", ytm_pct=ytm, coupon_pct=cp)
    status = TIER_TO_STATUS.get(bs.tier, "no_data")
    print(f"  {iid}: score={float(bs.score):.2f}  tier={bs.tier}  status={status}")
    print(f"        verdict: {expl.verdict}")
    print(f"        breakdown keys: {sorted(bs.breakdown.model_dump().keys())}")
print("-" * 70)
print("OK: scoring engine produced scores+tier+breakdown+explanation for all demo bonds")
