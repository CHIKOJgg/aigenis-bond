"""Regression tests for audit fixes.

1. Self-served partner keys (tier="trial") must NOT unlock premium analysis
   (K1) while listing/detail keep working.
2. P&L mark-to-market must convert money->face via the /100 factor (K8).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx

from api.main import app
from api.partner.security import generate_api_key
from scraper.db import dispose, get_engine, session_scope
from scraper.models import Bond
from scraper.orm import Base, BondORM, PartnerKeyORM, PortfolioPositionORM, TransactionORM

# --------------------------------------------------------------------------- #
# K1: trial-tier key gating
# --------------------------------------------------------------------------- #


def _trial_key_raw() -> str:
    raw, key_hash, key_fp = generate_api_key()
    return raw, key_hash, key_fp


def _add_key(session, *, tier: str, raw_hash: str, key_fp: str, name: str = "t") -> PartnerKeyORM:
    key = PartnerKeyORM(
        name=name,
        owner_user_id=None,
        key_hash=raw_hash,
        key_fp=key_fp,
        tier=tier,
        rate_limit=30 if tier == "trial" else 120,
        active=True,
    )
    session.add(key)
    return key


def _seed_bond(session) -> BondORM:
    b = BondORM(
        internal_id="TEST1",
        name="Test Bond",
        currency="USD",
        yield_to_maturity=Decimal("10"),
        price=Decimal("98.5"),
        status="active",
        maturity_date=date(2030, 1, 1),
        fetched_at=datetime.now(UTC),
        issuer="Treasury",
    )
    session.add(b)
    return b


def _run(coro_fn):
    async def wrapper():
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        try:
            await coro_fn()
        finally:
            await dispose()

    asyncio.run(wrapper())


def test_trial_key_cannot_access_analysis_but_can_list_and_detail():
    async def run():
        async with session_scope() as s:
            _seed_bond(s)
            raw, key_hash, key_fp = _trial_key_raw()
            _add_key(s, tier="trial", raw_hash=key_hash, key_fp=key_fp)

        transport = httpx.ASGITransport(app=app)
        headers = {"X-Aigenis-Api-Key": raw}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            listing = await client.get("/api/v1/partner/bonds", headers=headers)
            assert listing.status_code == 200

            detail = await client.get("/api/v1/partner/bonds/TEST1", headers=headers)
            assert detail.status_code == 200

            analysis = await client.get("/api/v1/partner/bonds/TEST1/analysis", headers=headers)
            assert analysis.status_code == 402

    _run(run)


def test_portal_partner_key_keeps_full_analysis():
    async def run():
        async with session_scope() as s:
            _seed_bond(s)
            raw, key_hash, key_fp = _trial_key_raw()
            _add_key(s, tier="partner", raw_hash=key_hash, key_fp=key_fp)

        transport = httpx.ASGITransport(app=app)
        headers = {"X-Aigenis-Api-Key": raw}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            analysis = await client.get("/api/v1/partner/bonds/TEST1/analysis", headers=headers)
            assert analysis.status_code == 200
            body = analysis.json()
            assert "analysis" in body

    _run(run)


# --------------------------------------------------------------------------- #
# K8: P&L money/face unit conversion on mark-to-market
# --------------------------------------------------------------------------- #

def test_pnl_marks_remaining_lots_at_face():
    from portfolio.pnl import compute_pnl

    txs = [
        TransactionORM(
            id=1,
            user_id=1,
            internal_id="B1",
            side="buy",
            amount=Decimal("1000"),
            price=Decimal("98"),
            currency="USD",
            executed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    positions = [
        PortfolioPositionORM(
            user_id=1,
            internal_id="B1",
            amount=Decimal("1000"),
            opened_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    # 1000 USD invested at 98 buys ~1020.41 of face; price later 100:
    # mark value = 1020.41, unrealized P&L = +20.41 (not 0 as before the fix).
    bonds = {
        "B1": Bond(
            internal_id="B1",
            name="B1",
            currency="USD",
            price=Decimal("100"),
            fetched_at=datetime.now(UTC),
        )
    }

    result = compute_pnl(transactions=txs, positions=positions, bonds_by_id=bonds)

    assert result.total_value == Decimal("1020.408163265306122448979592")  # face * 100/100
    assert result.total_unrealized == result.total_value - Decimal("1000")


def test_pnl_no_txs_keeps_par_entry_assumption():
    from portfolio.pnl import compute_pnl

    positions = [
        PortfolioPositionORM(
            user_id=1,
            internal_id="B2",
            amount=Decimal("1000"),
            opened_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    bonds = {"B2": Bond(internal_id="B2", name="B2", currency="USD", price=Decimal("110"), fetched_at=datetime.now(UTC))}

    result = compute_pnl(transactions=[], positions=positions, bonds_by_id=bonds)

    # Documented par-entry assumption: 1000 at par -> 1100 at price 110.
    assert result.total_value == Decimal("1100")
    assert result.total_unrealized == Decimal("100")
