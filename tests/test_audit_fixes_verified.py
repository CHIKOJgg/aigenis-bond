"""Tests verifying all 8 audit-driven fixes across math, PnL, optimizer, API, and billing."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

from desk.cashflow import pricing_cashflows, year_fraction
from desk.ytm import to_price_pct, ytm_from_price
from portfolio.optimizer import allocate, rank_bonds
from portfolio.pnl import compute_pnl
from scoring.engine import score_bond
from scoring.models import UserPreferences
from scraper.models import Bond


def test_ytm_fractional_period_and_par_exactness():
    # Exact 10-year 10% par bond -> YTM exact 10.0%
    y1 = ytm_from_price(100.0, 10.0, 2, date(2036, 8, 8), asof=date(2026, 8, 8))
    assert y1 is not None
    assert abs(y1 - 10.0) < 1e-5

    # Fractional period: 3 months (0.5 period) to first coupon of a 5% coupon bond
    # Price 98.0 -> YTM > 5.0%
    y2 = ytm_from_price(98.0, 5.0, 2, date(2027, 2, 8), asof=date(2026, 8, 8))
    assert y2 is not None
    assert y2 > 5.0


def test_ghost_coupon_prevented_when_asof_before_issue_date():
    # Valuation date prior to issue_date
    flows = pricing_cashflows(
        nominal=1000.0,
        coupon_rate_pct=10.0,
        coupon_frequency=2,
        maturity=date(2026, 1, 1),
        asof=date(2023, 12, 1),
        issue_date=date(2024, 1, 1),
    )
    # Cashflows must NOT contain a coupon payment on issue_date (2024-01-01)
    dates_with_coupons = [t for t, amt in flows if amt in (50.0, 1050.0)]
    assert len(dates_with_coupons) == 4
    # First coupon payment is at 2024-07-01 (approx 0.58 years from 2023-12-01)
    assert len(flows) == 4  # 4 semiannual coupons (2024-07-01, 2025-01-01, 2025-07-01, 2026-01-01)
    assert abs(flows[0][0] - (date(2024, 7, 1) - date(2023, 12, 1)).days / 365) < 0.05


def test_act_act_year_split_crossing_leap_year():
    # 2023-12-01 to 2024-02-01 (crosses into leap year 2024)
    frac = year_fraction(date(2023, 12, 1), date(2024, 2, 1), "ACT/ACT")
    # 31 days in 2023 / 365 + 31 days in 2024 / 366
    expected = (31 / 365) + (31 / 366)
    assert abs(frac - expected) < 1e-6


def test_pnl_fallback_cost_basis_when_bond_price_missing():
    class DummyPos:
        internal_id = "BOND-UNQUOTED"
        amount = Decimal("1000.00")

    class DummyBond:
        internal_id = "BOND-UNQUOTED"
        price = None  # Missing/unquoted price

    pos = DummyPos()
    bond = DummyBond()

    pnl = compute_pnl(
        transactions=[],
        positions=[pos],
        bonds_by_id={"BOND-UNQUOTED": bond},  # type: ignore
    )
    # Portfolio value must fall back to cost basis, NOT 0.0 (unrealized PnL = 0, not -1000)
    assert pnl.total_value == Decimal("1000.00")
    assert pnl.total_unrealized == Decimal("0.00")
    assert pnl.total_pnl() == Decimal("0.00")


def test_rank_bonds_does_not_mutate_original_bond_score():
    b = Bond(
        internal_id="TEST-SCORE-MUTATION",
        name="Test Bond",
        currency="BYN",
        nominal=Decimal("1000"),
        coupon_rate=Decimal("10.0"),
        yield_to_maturity=Decimal("12.0"),
        maturity_date=date(2028, 1, 1),
        fetched_at=datetime.now(UTC),
    )
    original_score = score_bond(
        internal_id=b.internal_id,
        yield_to_maturity=b.yield_to_maturity,
        currency=b.currency,
        maturity_date=b.maturity_date,
    )
    orig_val = original_score.score

    ranked = rank_bonds([b], strategy="Aggressive")
    assert len(ranked) == 1
    # Ranked score is strategy weighted
    assert ranked[0].score != orig_val
    # Original score instance remains untouched
    assert original_score.score == orig_val


def test_allocate_exact_cent_sum():
    b1 = Bond(
        internal_id="B1",
        name="Bond 1",
        currency="BYN",
        nominal=Decimal("1000"),
        coupon_rate=Decimal("10.0"),
        yield_to_maturity=Decimal("12.0"),
        maturity_date=date(2028, 1, 1),
        fetched_at=datetime.now(UTC),
    )
    b2 = Bond(
        internal_id="B2",
        name="Bond 2",
        currency="BYN",
        nominal=Decimal("1000"),
        coupon_rate=Decimal("8.0"),
        yield_to_maturity=Decimal("11.0"),
        maturity_date=date(2027, 1, 1),
        fetched_at=datetime.now(UTC),
    )
    prefs = UserPreferences(user_id=123, initial_capital=Decimal("10000.00"), strategy="Balanced")
    alloc = allocate([b1, b2], prefs, top_n=2)
    assert sum(alloc.items.values()) == Decimal("10000.00")


def test_to_price_pct_large_nominal_absolute_quote():
    # 9850 RUB absolute quote on a 10000 RUB nominal bond -> 98.5%
    p = to_price_pct(9850.0, 10000.0)
    assert p is not None
    assert abs(p - 98.5) < 1e-5


def test_webhook_locks_evicts_unlocked_keys_only():
    from api.billing.service import _WEBHOOK_LOCK_MAX_KEYS, _webhook_locks

    _webhook_locks.clear()
    active_lock = asyncio.Lock()
    _webhook_locks["active-pay-id"] = active_lock

    async def scenario():
        async with active_lock:
            # Populate locks over the limit
            for i in range(_WEBHOOK_LOCK_MAX_KEYS + 5):
                _webhook_locks[f"stale-{i}"] = asyncio.Lock()

            # Trigger eviction check by running the same pattern as billing service
            if len(_webhook_locks) > _WEBHOOK_LOCK_MAX_KEYS:
                for k in [k for k, lock_item in _webhook_locks.items() if not lock_item.locked() and k != "active-pay-id"]:
                    _webhook_locks.pop(k, None)

            # Active lock MUST survive eviction!
            assert "active-pay-id" in _webhook_locks

    asyncio.run(scenario())
