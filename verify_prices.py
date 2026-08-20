"""Check that each demo bond's stated price is consistent with its stated YTM
and coupon schedule (price accuracy audit)."""

import json
from datetime import date
from pathlib import Path

from desk.ytm import to_price_pct, ytm_from_price

REPO = Path(__file__).resolve().parent
bad = 0
for f in ["demo-data/v1/bonds_bcse.json", "demo-data/v1/bonds_moex.json"]:
    for b in json.loads((REPO / f).read_text(encoding="utf-8")):
        if b.get("income_method") == "indexed":
            continue
        asof = date.fromisoformat(b["fetched_at"][:10])
        pp = to_price_pct(b["price"], b["nominal"])
        y = ytm_from_price(
            pp,
            b["coupon_rate"],
            b["coupon_frequency"],
            date.fromisoformat(b["maturity_date"]),
            asof,
        )
        stated = b.get("yield_to_maturity") or 0.0
        ok = y is not None and abs(y - stated) < 0.15
        flag = "" if ok else "  <-- MISMATCH"
        if not ok:
            bad += 1
        print(
            f"{b['internal_id']:28} price={b['price']:7} pp={pp:7} "
            f"statedYTM={stated:6} solvedYTM={None if y is None else round(y, 3)}{flag}"
        )
print(f"\nPrice/YTM mismatches: {bad}")
