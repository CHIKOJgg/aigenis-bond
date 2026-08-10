"""Independent numerical verification of YTM / duration / scoring math.

Run inside the parser container (or any env with the repo deps):
    docker compose run --rm -v ${PWD}/verify-calcs.py:/app/verify-calcs.py parser python3 verify-calcs.py
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal

from desk.cashflow import accrued_interest
from desk.duration import convexity, macaulay_duration, modified_duration
from desk.ytm import to_price_pct, ytm_from_price

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "OK " if cond else "FAIL"
    print(f"  [{status}] {name} {detail}")
    if not cond:
        failures.append(name)


print("== 1. YTM solver ==")
# Classic: 10% coupon, semi-annual, 10y, price=100 -> YTM == 10%
y = ytm_from_price(100.0, 10.0, 2, date(2036, 8, 8), asof=date(2026, 8, 8))
check("par bond ytm == coupon (10%)", y is not None and abs(y - 10.0) < 0.01, f"got {y}")

# 5% coupon, annual, 5y, price=95 -> YTM ~ 6.21% (true root of the PV equation)
y = ytm_from_price(95.0, 5.0, 1, date(2031, 8, 8), asof=date(2026, 8, 8))
check("below-par ytm > coupon (5%/95 -> ~6.21%)", y is not None and abs(y - 6.21) < 0.1, f"got {y}")

# Zero coupon, 3y, price=85 -> YTM = (100/85)^(1/3)-1 = 5.57%
y = ytm_from_price(85.0, 0.0, 1, date(2029, 8, 8), asof=date(2026, 8, 8))
expected = ((100 / 85) ** (1 / 3) - 1) * 100
check(
    "zero-coupon ytm matches (100/85)^(1/3)-1",
    y is not None and abs(y - expected) < 0.05,
    f"got {y}, expected {expected}",
)

# Price 0 / negative / no maturity -> None
check(
    "ytm guards bad inputs",
    ytm_from_price(0.0, 10.0, 2, date(2030, 1, 1)) is None
    and ytm_from_price(-5.0, 10.0, 2, date(2030, 1, 1)) is None
    and ytm_from_price(100.0, 10.0, 2, date(2020, 1, 1)) is None,
)

# 10y bond at par, high coupon: YTM stays == coupon
y = ytm_from_price(100.0, 14.5, 2, date(2031, 1, 1), asof=date(2026, 1, 1))
check("14.5% par bond ytm == 14.5%", y is not None and abs(y - 14.5) < 0.01, f"got {y}")

print("== 2. to_price_pct normalization ==")
check(
    "absolute price 10039.58 on 10000 nominal -> 100.396%",
    abs((to_price_pct(10039.58, 10000.0) or 0) - 100.3958) < 1e-6,
)
check("percent price 99.5 passes through", abs((to_price_pct(99.5, 1000.0) or 0) - 99.5) < 1e-9)
check(
    "percent 100.0 on 200 nominal stays 100.0 (regression: was 50%)",
    abs((to_price_pct(100.0, 200.0) or 0) - 100.0) < 1e-9,
)
check(
    "percent 100.0 on 50 nominal stays 100.0 (regression: was 200%)",
    abs((to_price_pct(100.0, 50.0) or 0) - 100.0) < 1e-9,
)
check("None/0 -> None", to_price_pct(None, 1000.0) is None and to_price_pct(0, 1000.0) is None)

print("== 3. Macaulay duration ==")
# Zero-coupon 3y -> duration == time to maturity (ACT/365: 1096/365 = 3.0027)
d = macaulay_duration(
    nominal=Decimal(1000),
    coupon_rate_pct=0.0,
    coupon_frequency=1,
    ytm_pct=5.57,
    maturity=date(2029, 8, 8),
    ref=date(2026, 8, 8),
)
check("zero-coupon macaulay == time to maturity (3.0027y)", abs(d - 3.00274) < 1e-4, f"got {d}")

# Par bond 10% 10y semi-annual -> textbook Macaulay ~6.54
d = macaulay_duration(
    nominal=Decimal(1000),
    coupon_rate_pct=10.0,
    coupon_frequency=2,
    ytm_pct=10.0,
    maturity=date(2036, 8, 8),
    ref=date(2026, 8, 8),
)
check("10y par 10% bond duration ~6.54y", abs(d - 6.54) < 0.05, f"got {d}")

# Modified < Macaulay for positive yield
mac = macaulay_duration(
    nominal=Decimal(1000),
    coupon_rate_pct=10.0,
    coupon_frequency=2,
    ytm_pct=10.0,
    maturity=date(2036, 8, 8),
    ref=date(2026, 8, 8),
)
mod = modified_duration(
    nominal=Decimal(1000),
    coupon_rate_pct=10.0,
    coupon_frequency=2,
    ytm_pct=10.0,
    maturity=date(2036, 8, 8),
    ref=date(2026, 8, 8),
)
check("modified < macaulay", mod < mac, f"mac={mac} mod={mod}")

# Convexity positive for standard bond (textbook ~52.9 for 10y par 10%)
cvx = convexity(
    nominal=Decimal(1000),
    coupon_rate_pct=10.0,
    coupon_frequency=2,
    ytm_pct=10.0,
    maturity=date(2036, 8, 8),
    ref=date(2026, 8, 8),
)
check("convexity > 0 (~52.9)", cvx > 0 and abs(cvx - 52.9) < 5.0, f"got {cvx}")

print("== 4. Accrued interest ==")
# Day after the coupon date -> ~0 (accrual restarted); just before next coupon -> ~full
acc = accrued_interest(
    coupon_rate_pct=10.0,
    coupon_frequency=2,
    issue_date=date(2026, 2, 10),
    maturity_date=date(2036, 2, 10),
    asof=date(2026, 8, 11),
)
check("day after coupon -> ~0", acc is not None and acc < 0.1, f"got {acc}")
acc = accrued_interest(
    coupon_rate_pct=10.0,
    coupon_frequency=2,
    issue_date=date(2026, 2, 10),
    maturity_date=date(2036, 2, 10),
    asof=date(2027, 2, 9),
)
check("just before coupon -> ~full 5.0", acc is not None and abs(acc - 5.0) < 0.05, f"got {acc}")

print("== 5. Score engine sanity ==")
from scoring.engine import score_bond  # noqa: E402

bs = score_bond(
    internal_id="t1",
    yield_to_maturity=14.2,
    currency="BYN",
    maturity_date=date(2028, 6, 15),
    status="active",
    issuer="Минфин РБ",
    price=98.5,
    nominal=Decimal("100"),
    coupon_rate=12.5,
    market="bcse",
)
bd = bs.breakdown
check("score in [0,100]", 0 <= bs.score <= 100, f"score={bs.score}")
check("tier in S/A/B/C/D", bs.tier in ("S", "A", "B", "C", "D"), f"tier={bs.tier}")
reward_comps = [
    bd.yield_component,
    bd.currency_component,
    bd.duration_component,
    bd.liquidity_component,
    bd.metal_component,
    bd.credit_risk_component,
    bd.inflation_component,
    bd.coupon_component,
    bd.historical_volatility_component,
    bd.peer_relative_component,
]
check(
    "reward_subtotal = sum of positive comps (excl. volatility)",
    abs(bd.reward_subtotal - sum(max(v, 0.0) for v in reward_comps)) < 1e-6,
    f"subtotal={bd.reward_subtotal}",
)
risk_comps = [*reward_comps, bd.volatility_component]
check(
    "risk_subtotal = sum of |negative comps|",
    abs(bd.risk_subtotal - sum(abs(min(v, 0.0)) for v in risk_comps)) < 1e-6,
    f"risk={bd.risk_subtotal}",
)
expected_eff = (bd.reward_subtotal / (bd.reward_subtotal + bd.risk_subtotal + 1.0)) * 15.0
check(
    "efficiency = reward/(reward+risk+1)*15 (2dp rounding)",
    abs(bd.efficiency_ratio - expected_eff) < 0.005,
    f"eff={bd.efficiency_ratio}, expected={expected_eff}",
)
check(
    "score = reward - risk (all comps net)",
    abs(bs.score - (bd.reward_subtotal - bd.risk_subtotal)) < 1e-6,
    f"score={bs.score} net={bd.reward_subtotal - bd.risk_subtotal}",
)
check(
    "high YTM + low risk -> attractive status",
    bs.tier in ("S", "A", "B") or bs.score >= 70,
    f"tier={bs.tier} score={bs.score}",
)

bs2 = score_bond(
    internal_id="t2",
    yield_to_maturity=3.0,
    currency="RUB",
    maturity_date=date(2035, 1, 1),
    status="active",
    issuer="ОФЗ",
    price=90.0,
    nominal=Decimal("100"),
    coupon_rate=4.0,
    market="moex",
)
check(
    "low yield -> not attractive",
    bs2.tier in ("C", "D") or bs2.score < 60,
    f"tier={bs2.tier} score={bs2.score}",
)

print()
if failures:
    print(f"RESULT: FAIL ({len(failures)} failures): {failures}")
    sys.exit(1)
print("RESULT: ALL CHECKS PASSED")
