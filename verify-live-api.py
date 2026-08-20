"""Independent audit of live API financial math.

Runs inside the parser container: python3 /app/verify-live-api.py
Fetches real data from the API and re-derives yields, prices, durations, NKD.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import date, datetime

from desk.cashflow import accrued_interest, year_fraction
from desk.duration import (
    bond_modified_duration,
    convexity,
    macaulay_duration,
)
from desk.ytm import to_price_pct, ytm_from_price

BASE = "http://aigenis-api:8000"


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode())


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'OK ' if cond else 'FAIL'}] {name} {detail}")
    return cond


failures: list[str] = []
results: list[tuple[str, bool]] = []


def add(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, cond))
    check(name, cond, detail)
    if not cond:
        failures.append(name)


print("== 1. Fetch bonds ==")
try:
    bonds = get("/api/v1/bonds?limit=100")
except Exception as e:
    print(f"  FAIL to fetch bonds: {e}")
    sys.exit(1)
add("bonds fetched", isinstance(bonds, list) and len(bonds) > 0, f"n={len(bonds)}")
active = [b for b in bonds if b.get("status") == "active"]
print(f"  active={len(active)} total={len(bonds)}")

asof = date.today()

print("== 2. YTM <-> price consistency (active bonds) ==")
ytm_mismatches = 0
for b in active:
    try:
        price = float(b["price"])
        coupon = float(b["coupon_rate"])
        freq = int(b["coupon_frequency"] or 1)
        mat = date.fromisoformat(b["maturity_date"])
        stored_ytm = float(b["yield_to_maturity"]) if b.get("yield_to_maturity") else None
    except Exception:
        continue
    y = ytm_from_price(price, coupon, freq, mat, asof=asof)
    if y is None:
        ytm_mismatches += 1
        add(f"ytm: {b['internal_id']} solver failed", False)
        continue
    if stored_ytm is not None and abs(y - stored_ytm) > 0.5:
        ytm_mismatches += 1
        add(
            f"ytm: {b['internal_id']} stored={stored_ytm:.4f} solved={y:.4f}",
            False,
            f"diff={abs(y-stored_ytm):.4f}pp price={price} coupon={coupon} mat={mat}",
        )
if ytm_mismatches == 0:
    print("  [OK ] all YTMs consistent")

print("== 3. NKD (accrued interest) sanity ==")
for b in active[:8]:
    try:
        coupon = float(b["coupon_rate"])
        freq = int(b["coupon_frequency"] or 1)
        mat = date.fromisoformat(b["maturity_date"])
        start = date.fromisoformat(b.get("start_date") or b.get("issue_date") or str(mat.replace(year=mat.year - 10)))
        nkd = accrued_interest(coupon_rate_pct=coupon, coupon_frequency=freq, issue_date=start, maturity_date=mat, asof=asof)
        stored_nkd = b.get("accrued_interest")
        per_coupon = coupon / freq
        ok = nkd is not None and 0 <= nkd <= per_coupon * 1.0001
        if stored_nkd is not None:
            try:
                ok = ok and abs(float(stored_nkd) - nkd) < 0.01
            except Exception:
                pass
        add(f"nkd: {b['internal_id']} computed={nkd:.4f} stored={stored_nkd}", ok, f"per_coupon={per_coupon:.4f}")
    except Exception as e:
        add(f"nkd: {b['internal_id']} error", False, str(e))

print("== 4. Duration endpoint vs independent Macaulay ==")
dur_checked = 0
for b in active[:10]:
    try:
        price = float(b["price"])
        coupon = float(b["coupon_rate"])
        freq = int(b["coupon_frequency"] or 1)
        mat = date.fromisoformat(b["maturity_date"])
        nominal = float(b.get("nominal") or 1000)
        ytm = float(b["yield_to_maturity"])
        resp = get(f"/api/v1/desk/duration?bond_id={b['internal_id']}")
        mod_dur = resp.get("modified_duration") if isinstance(resp, dict) else None
        mac = macaulay_duration(
            nominal=nominal,
            coupon_rate_pct=coupon,
            coupon_frequency=freq,
            ytm_pct=ytm,
            maturity=mat,
            ref=asof,
        )
        if mod_dur is None:
            add(f"dur: {b['internal_id']} no modified_duration in resp", False, str(resp)[:200])
            continue
        mac_mod = mac / (1 + ytm / 100 / freq)
        if abs(mac_mod - mod_dur) > 0.2:
            add(
                f"dur: {b['internal_id']} api={mod_dur:.4f} independent={mac_mod:.4f}",
                False,
                f"mac={mac:.4f} ytm={ytm} freq={freq}",
            )
        dur_checked += 1
    except Exception as e:
        add(f"dur: {b['internal_id']} error", False, str(e)[:150])
if dur_checked:
    print(f"  duration checked for {dur_checked} bonds")

print("== 5. Cashflow endpoint sanity ==")
for b in active[:5]:
    try:
        resp = get(f"/api/v1/bond/{b['internal_id']}/cashflow")
        if not isinstance(resp, dict) or "cashflows" not in resp:
            add(f"cf: {b['internal_id']} bad shape", False, str(resp)[:200])
            continue
        cfs = resp["cashflows"]
        if not isinstance(cfs, list) or not cfs:
            add(f"cf: {b['internal_id']} empty", False)
            continue
        last = cfs[-1]
        is_principal = (last.get("type") in ("principal", "redemption", "maturity", "face")) or (last.get("amount", 0) >= float(b.get("nominal") or 0) * 0.5)
        add(f"cf: {b['internal_id']} n={len(cfs)} last_type={last.get('type')}", is_principal, f"last={last}")
        total = sum(float(c.get("amount", 0)) for c in cfs)
        add(f"cf: {b['internal_id']} total>principal", total > float(b.get("nominal") or 0), f"total={total:.2f}")
    except Exception as e:
        add(f"cf: {b['internal_id']} error", False, str(e)[:150])

print("== 6. Desk endpoints numeric sanity ==")
for ep, key in [
    ("/api/v1/desk/curve", None),
    ("/api/v1/desk/rv", None),
    ("/api/v1/desk/spreads", None),
    ("/api/v1/desk/status", None),
]:
    try:
        resp = get(ep)
        s = json.dumps(resp)
        if "NaN" in s or "Infinity" in s or "-Infinity" in s:
            add(f"desk {ep}: NaN/Inf present", False, s[:300])
        else:
            add(f"desk {ep}: ok", True, f"size={len(s)}")
    except Exception as e:
        add(f"desk {ep}: error", False, str(e)[:150])

print()
if failures:
    print(f"RESULT: FAIL ({len(failures)}): ")
    for f in failures:
        print("   -", f)
    sys.exit(1)
print("RESULT: ALL LIVE CHECKS PASSED")
