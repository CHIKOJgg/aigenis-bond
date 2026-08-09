"""Tests for scraper/repositories (bonds, history, stocks) against SQLite."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scraper.db import session_scope
from scraper.models import Bond, BondDailyAccrual, BondHistory, Stock, StockHistory
from scraper.repositories.bonds import (
    BOND_NAME_MAP,
    _enrich_bond_name,
    _is_technical_name,
    count_bonds,
    exists,
    get_all_internal_ids,
    get_by_currency,
    latest_fetched_at,
    register_xlsx_names,
    update_bond_name,
    upsert_bond,
    upsert_bonds_batch,
)
from scraper.repositories.history import (
    bond_history_since,
    count_history,
    last_accrual_date,
    last_history_date,
    upsert_accruals_batch,
    upsert_history_batch,
)
from scraper.repositories.stocks import (
    count_stock_history,
    count_stocks,
    get_all_stock_internal_ids,
    get_stock_by_internal_id,
    get_stocks_by_board,
    last_stock_history_date,
    latest_stock_fetched_at,
    upsert_stock,
    upsert_stock_history_batch,
    upsert_stocks_batch,
)


def _bond(internal_id: str, **kw) -> Bond:
    base = dict(
        internal_id=internal_id,
        name="Bond Name",
        issuer="Issuer",
        currency="USD",
        nominal=Decimal("1000"),
        coupon_rate=Decimal("5.0"),
        coupon_frequency=2,
        maturity_date=date(2030, 1, 1),
        price=Decimal("100"),
        yield_to_maturity=Decimal("8.0"),
        isin=f"RU000{internal_id}",
        market="bcse",
        status="active",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(kw)
    return Bond(**base)


def _stock(internal_id: str, **kw) -> Stock:
    base = dict(
        internal_id=internal_id,
        secid=internal_id,
        name="Stock Name",
        board="TQBR",
        currency="RUB",
        price=Decimal("100"),
        value_traded=Decimal("1000"),
        status="active",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(kw)
    return Stock(**base)


def test_is_technical_name():
    assert _is_technical_name("")
    assert _is_technical_name("B-001")
    assert _is_technical_name("OP-30")
    assert not _is_technical_name("Айгенис Оп 30")
    assert not _is_technical_name("Some Bond 2028")


def test_enrich_bond_name():
    assert _enrich_bond_name(_bond("OP-30")) == "iGenis OP30"
    named = _bond("X1", name="Хорошее Имя Облигации")
    assert _enrich_bond_name(named) == "Хорошее Имя Облигации"
    issuer_no_number = _bond("X2", name="OP-12", issuer="ООО Эмитент")
    assert _enrich_bond_name(issuer_no_number) == "Эмитент"
    issuer_with_number = _bond("X3", name="OP-12", issuer="ООО Эмитент", issue_number=3)
    assert _enrich_bond_name(issuer_with_number) == "Эмитент #3"
    technical_issuer = _bond("X4", name="OP-12", issuer="RUS-2028-01")
    assert _enrich_bond_name(technical_issuer) == "X4"
    digits = _bond("42", name="42", issuer=None)
    assert _enrich_bond_name(digits) == "Выпуск #42"
    plain = _bond("MF-LB-USD-0265", name="", issuer=None)
    assert _enrich_bond_name(plain) == "MF LB USD 0265"


def test_register_xlsx_names():
    try:
        register_xlsx_names({"OP-99": "Новое имя"})
        assert BOND_NAME_MAP["OP-99"] == "Новое имя"
        assert _enrich_bond_name(_bond("OP-99")) == "Новое имя"
    finally:
        BOND_NAME_MAP.pop("OP-99", None)


@pytest.mark.asyncio
async def test_upsert_bond_and_queries():
    async with session_scope() as session:
        await upsert_bond(session, _bond("RB-1", currency="USD"))
        await upsert_bond(session, _bond("RB-2", currency="BYN", yield_to_maturity=Decimal("12")))
        await upsert_bond(session, _bond("RB-3", currency="USD", yield_to_maturity=Decimal("6")))
        assert await count_bonds(session) >= 3
        assert await exists(session, "RB-1") is True
        assert await exists(session, "RB-MISSING") is False
        ids = await get_all_internal_ids(session)
        assert "RB-1" in ids
        usd = await get_by_currency(session, "USD")
        assert [b.internal_id for b in usd] == ["RB-1", "RB-3"]
        assert await latest_fetched_at(session) is not None


@pytest.mark.asyncio
async def test_upsert_bond_overwrites_and_empty_batch():
    async with session_scope() as session:
        await upsert_bond(session, _bond("RB-10", price=Decimal("100")))
        await upsert_bond(session, _bond("RB-10", price=Decimal("95")))
        found = await session.get(__import__("scraper.orm", fromlist=["BondORM"]).BondORM, "RB-10")
        assert float(found.price) == 95.0
        assert await upsert_bonds_batch(session, []) == 0
        n = await upsert_bonds_batch(session, [_bond("RB-20"), _bond("RB-21")])
        assert n == 2
        await upsert_bonds_batch(session, [_bond("RB-20", price=Decimal("88"))])
        found = await session.get(__import__("scraper.orm", fromlist=["BondORM"]).BondORM, "RB-20")
        assert float(found.price) == 88.0


@pytest.mark.asyncio
async def test_update_bond_name():
    async with session_scope() as session:
        await upsert_bond(session, _bond("RB-30"))
        await update_bond_name(session, "RB-30", "Новое имя")
        found = await session.get(__import__("scraper.orm", fromlist=["BondORM"]).BondORM, "RB-30")
        assert found is not None and found.name == "Новое имя"
        await update_bond_name(session, "RB-30", "Ещё новее")
        found = await session.get(__import__("scraper.orm", fromlist=["BondORM"]).BondORM, "RB-30")
        assert found.name == "Ещё новее"


def _bhistory(internal_id: str, day: int, **kw) -> BondHistory:
    values = dict(
        price=Decimal("100"),
        yield_=Decimal("8"),
        status="active",
    )
    values.update(kw)
    return BondHistory(internal_id=internal_id, date=date(2026, 1, day), **values)


@pytest.mark.asyncio
async def test_history_upsert_and_queries():
    async with session_scope() as session:
        assert await upsert_history_batch(session, []) == 0
        n = await upsert_history_batch(
            session,
            [_bhistory("RH-1", 2), _bhistory("RH-1", 3), _bhistory("RH-2", 2)],
        )
        assert n == 3
        assert await count_history(session) >= 3
        assert await last_history_date(session, "RH-1") == date(2026, 1, 3)
        assert await last_history_date(session, "RH-MISSING") is None
        since = await bond_history_since(session, "RH-1", date(2026, 1, 3))
        assert [h.date for h in since] == [date(2026, 1, 3)]
        await upsert_history_batch(session, [_bhistory("RH-1", 3, price=Decimal("99"))])
        since = await bond_history_since(session, "RH-1", date(2026, 1, 1))
        assert float(since[-1].price) == 99.0


@pytest.mark.asyncio
async def test_accruals_upsert():
    async with session_scope() as session:
        assert await upsert_accruals_batch(session, []) == 0
        rows = [
            BondDailyAccrual(internal_id="RA-1", date=date(2026, 1, 2), accrued=Decimal("1.5")),
            BondDailyAccrual(internal_id="RA-1", date=date(2026, 1, 3), accrued=Decimal("2.5")),
        ]
        assert await upsert_accruals_batch(session, rows) == 2
        assert await last_accrual_date(session, "RA-1") == date(2026, 1, 3)
        assert await last_accrual_date(session, "RA-MISSING") is None


@pytest.mark.asyncio
async def test_stocks_upsert_and_queries():
    async with session_scope() as session:
        await upsert_stock(session, _stock("SBER", board="TQBR", value_traded=Decimal("5000")))
        await upsert_stock(session, _stock("GAZP", board="TQBR", value_traded=Decimal("9000")))
        await upsert_stock(session, _stock("VTBR", board="TQOD", value_traded=Decimal("100")))
        assert await count_stocks(session) >= 3
        ids = await get_all_stock_internal_ids(session)
        assert "SBER" in ids and "GAZP" in ids
        tqbr = await get_stocks_by_board(session, "TQBR")
        assert [s.internal_id for s in tqbr] == ["GAZP", "SBER"]
        assert (await get_stock_by_internal_id(session, "SBER")).secid == "SBER"
        assert await get_stock_by_internal_id(session, "MISSING") is None
        assert await latest_stock_fetched_at(session) is not None
        assert await upsert_stocks_batch(session, []) == 0
        await upsert_stocks_batch(
            session, [_stock("MOEX", board="TQBR"), _stock("LKOH", board="TQBR")]
        )
        assert await count_stocks(session) >= 5
        await upsert_stock(session, _stock("SBER", price=Decimal("300")))
        found = await get_stock_by_internal_id(session, "SBER")
        assert float(found.price) == 300.0


@pytest.mark.asyncio
async def test_stock_history_upsert():
    async with session_scope() as session:
        assert await upsert_stock_history_batch(session, []) == 0
        rows = [
            StockHistory(internal_id="SBER", date=date(2026, 1, 2), close_price=Decimal("250")),
            StockHistory(internal_id="SBER", date=date(2026, 1, 3), close_price=Decimal("260")),
        ]
        assert await upsert_stock_history_batch(session, rows) == 2
        assert await count_stock_history(session) >= 2
        assert await last_stock_history_date(session, "SBER") == date(2026, 1, 3)
        assert await last_stock_history_date(session, "MISSING") is None


@pytest.mark.asyncio
async def test_instrument_summary_and_search():
    from scraper.repositories.instruments import instrument_summary, search_instruments

    async with session_scope() as session:
        await upsert_bond(
            session,
            _bond(
                "IS-1",
                name="Газпром Облигация",
                issuer="Газпром",
                yield_to_maturity=Decimal("8.5"),
            ),
        )
        await upsert_stock(
            session,
            _stock("IS-2", name="Газпром Акция", dividend_yield=Decimal("5.5")),
        )
        await upsert_stock(session, _stock("IS-3", name="Сбер Акция", pbr_ratio=Decimal("1.2")))
        await upsert_stock(session, _stock("IS-4", name="Простая Акция"))

        bond_sum = await instrument_summary(session, "IS-1")
        assert bond_sum is not None and bond_sum.asset_class == "bond"
        assert bond_sum.headline == "Доходность 8.5000%"
        assert bond_sum.market == "bcse"

        div_stock = await instrument_summary(session, "IS-2")
        assert div_stock is not None and div_stock.asset_class == "equity"
        assert div_stock.headline == "Див. доходность 5.5000%"
        assert div_stock.market == "TQBR"

        pbr_stock = await instrument_summary(session, "IS-3")
        assert pbr_stock.headline == "P/B 1.2000"

        plain_stock = await instrument_summary(session, "IS-4")
        assert plain_stock.headline is None

        assert await instrument_summary(session, "IS-MISSING") is None

        hits = await search_instruments(session, "Газпром")
        assert {h.internal_id for h in hits} == {"IS-1", "IS-2"}
        by_id = await search_instruments(session, "IS-2")
        assert {h.internal_id for h in by_id} == {"IS-2"}
        empty = await search_instruments(session, "zzzz")
        assert empty == []


@pytest.mark.asyncio
async def test_search_instruments_bond_limit():
    from scraper.repositories.instruments import search_instruments

    async with session_scope() as session:
        await upsert_bonds_batch(
            session,
            [
                _bond("SB-1", name="SearchBond 1", issuer="Газпром"),
                _bond("SB-2", name="SearchBond 2", issuer="Газпром"),
                _bond("SB-3", name="SearchBond 3", issuer="Газпром"),
            ],
        )
        await upsert_stock(session, _stock("SB-4", name="SearchBond 4"))
        hits = await search_instruments(session, "SearchBond", limit=3)
        assert {h.internal_id for h in hits} == {"SB-1", "SB-2", "SB-3"}
        more = await search_instruments(session, "SearchBond", limit=10)
        assert len(more) == 4
