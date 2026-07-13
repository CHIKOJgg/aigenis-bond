"""Tests for coupon income projection (cashflows + portfolio income calendar)."""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx

from api.auth.service import create_access_token
from api.main import app
from portfolio.income import annual_income, bond_cashflows, portfolio_income
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, BondORM, UserORM


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _run(coro_fn):
    async def wrapper():
        await _ensure_schema()
        try:
            await coro_fn()
        finally:
            await dispose()

    asyncio.run(wrapper())


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


# --------------------------------------------------------------------------- #
# Pure math
# --------------------------------------------------------------------------- #
def test_bond_cashflows_semiannual():
    maturity = date.today().replace(year=date.today().year + 2)
    flows = bond_cashflows(
        internal_id="OP-1",
        amount_invested=Decimal("10000"),
        coupon_rate=Decimal("10"),
        coupon_frequency=2,
        maturity_date=maturity,
        price=Decimal("100"),
    )
    coupons = [f for f in flows if f.kind == "coupon"]
    redemptions = [f for f in flows if f.kind == "redemption"]
    # ~2 years, semiannual -> ~4 coupons.
    assert 3 <= len(coupons) <= 4
    # 10% on 10000 face, semiannual -> 500 each.
    assert coupons[0].amount == Decimal("500.00")
    # Exactly one principal redemption at maturity.
    assert len(redemptions) == 1
    assert redemptions[0].date == maturity
    assert redemptions[0].amount == Decimal("10000.00")


def test_face_value_uses_price_discount():
    # Buying at 80 gets more face value -> larger coupons.
    ann = annual_income(
        amount_invested=Decimal("8000"), coupon_rate=Decimal("10"), price=Decimal("80")
    )
    # face = 8000 * 100 / 80 = 10000 -> 10% = 1000.
    assert ann == Decimal("1000.00")


def test_no_coupon_returns_only_redemption():
    maturity = date.today().replace(year=date.today().year + 1)
    flows = bond_cashflows(
        internal_id="Z-1",
        amount_invested=Decimal("1000"),
        coupon_rate=None,
        coupon_frequency=None,
        maturity_date=maturity,
        price=Decimal("100"),
    )
    assert all(f.kind == "redemption" for f in flows)
    assert len(flows) == 1


def test_matured_bond_has_no_future_flows():
    past = date.today() - timedelta(days=10)
    flows = bond_cashflows(
        internal_id="OLD",
        amount_invested=Decimal("1000"),
        coupon_rate=Decimal("10"),
        coupon_frequency=2,
        maturity_date=past,
        price=Decimal("100"),
    )
    assert flows == []


def test_portfolio_income_aggregates():
    maturity = date.today().replace(year=date.today().year + 3)
    holdings = [
        {
            "internal_id": "A",
            "amount": 10000,
            "coupon_rate": Decimal("10"),
            "coupon_frequency": 2,
            "maturity_date": maturity,
            "price": Decimal("100"),
            "name": "A",
            "currency": "USD",
        },
        {
            "internal_id": "B",
            "amount": 5000,
            "coupon_rate": Decimal("8"),
            "coupon_frequency": 1,
            "maturity_date": maturity,
            "price": Decimal("100"),
            "name": "B",
            "currency": "BYN",
        },
    ]
    result = portfolio_income(holdings)
    assert result["total_invested"] == 15000.0
    # 1000 (A) + 400 (B) = 1400 annual.
    assert result["annual_income"] == 1400.0
    assert result["yield_on_cost"] == round(1400 / 15000 * 100, 2)
    assert result["next_payment"] is not None
    assert len(result["per_bond"]) == 2
    assert result["per_bond"][0]["internal_id"] == "A"  # sorted by income desc


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
async def _seed():
    async with session_scope() as s:
        s.add(
            UserORM(
                id=1,
                email="pro@example.com",
                name="Pro",
                password_hash="x",
                role="user",
                is_active=True,
                is_verified=False,
                subscription_tier="pro",
                subscription_expires_at=datetime.now(UTC) + timedelta(days=30),
            )
        )
        s.add(
            BondORM(
                internal_id="OP-1",
                name="USD Bond",
                currency="USD",
                yield_to_maturity=10.0,
                coupon_rate=10.0,
                coupon_frequency=2,
                price=100.0,
                status="active",
                maturity_date=date.today().replace(year=date.today().year + 2),
                fetched_at=datetime.now(UTC),
            )
        )


def test_cashflow_endpoint_gated_and_works():
    async def run():
        await _seed()
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/bond/OP-1/cashflow?amount=10000")
            assert resp.status_code == 402

            resp = await client.get(
                "/api/v1/bond/OP-1/cashflow?amount=10000", headers=_auth(1)
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["annual_income"] == 1000.0
            assert body["cashflows"]
            assert any(f["kind"] == "redemption" for f in body["cashflows"])

    _run(run)


def test_portfolio_income_endpoint():
    async def run():
        await _seed()
        headers = _auth(1)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Empty first.
            resp = await client.get("/api/v1/portfolio/income", headers=headers)
            assert resp.status_code == 200
            assert resp.json()["mode"] == "empty"

            await client.post(
                "/api/v1/positions", headers=headers,
                json={"internal_id": "OP-1", "amount": 10000},
            )
            resp = await client.get("/api/v1/portfolio/income", headers=headers)
            assert resp.status_code == 200
            body = resp.json()
            assert body["mode"] == "portfolio"
            assert body["annual_income"] == 1000.0
            assert body["yield_on_cost"] == 10.0
            assert body["next_payment"] is not None
            assert body["monthly_calendar"]

    _run(run)
