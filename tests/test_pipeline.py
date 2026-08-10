"""Tests for scraper/pipeline: collect_*, backfill_history, enrich_from_xlsx, run_once*."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scraper.db import session_scope
from scraper.errors import (
    HistoryUnavailable,
    NotFoundError,
    ParseError,
    ScraperError,
    TransientError,
)
from scraper.models import Bond, BondDailyAccrual, BondHistory, Stock, StockHistory
from scraper.orm import BondHistoryORM, BondORM, StockORM

CURRENCIES = ("USD", "BYN")

LISTING_ITEMS = [
    {"symbol": "P-1", "name": "Bond P1", "currency": "USD"},
    {"symbol": "P-2", "name": "Bond P2", "currency": "USD"},
    {"symbol": "P-3", "name": "Bond P3", "currency": "USD"},
    {"symbol": "P-1", "name": "Bond P1 again", "currency": "BYN"},
]

DETAIL_PAYLOAD = {
    "id": "P-1",
    "name": "Bond P1",
    "currency": "USD",
    "status": "active",
    "yield_to_maturity": "8.5",
    "price": "101.5",
}

HISTORY_PAYLOAD = [
    {"date": "2026-01-02", "price": "101", "yield": "8.2"},
    {"date": "2026-01-03", "price": "102", "yield": "8.1"},
]


class FakeClient:
    """Mimics the AigenisClient surface used by the pipeline."""

    def __init__(self, settings=None) -> None:
        self.settings = settings or SimpleNamespace(
            max_concurrency=4,
            history_backfill_days=30,
            data_provider="aigenis",
            license_contract_id="lic-1",
        )
        self._id_by_internal: dict[str, str] = {}
        self.listing_errors: dict[str, BaseException] = {}
        self.detail_errors: dict[str, BaseException] = {}
        self.history_error: BaseException | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def fetch_listing(self, currency):
        if currency in self.listing_errors:
            raise self.listing_errors[currency]
        return {"items": LISTING_ITEMS, "currency": currency}

    async def fetch_detail(self, iid):
        if iid in self.detail_errors:
            raise self.detail_errors[iid]
        return {**DETAIL_PAYLOAD, "id": iid}

    async def fetch_history(self, iid, since, today):
        if self.history_error:
            raise self.history_error
        return HISTORY_PAYLOAD

    async def fetch_coupons(self, iid):
        return [{"date": date(2026, 1, 15), "coupon": Decimal("4")}]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("12.5", Decimal("12.5")),
        (Decimal("7"), Decimal("7")),
        ("abc", None),
    ],
)
def test_d(value, expected):
    from scraper.pipeline import _d

    assert _d(value) == expected


# ------------------------------------------------------------ collect_listing ---


@pytest.mark.asyncio
async def test_collect_listing_dedupes_and_tolerates_failures(caplog):
    from scraper.pipeline import collect_listing

    client = FakeClient()
    client.listing_errors["BYN"] = RuntimeError("network down")
    result = await collect_listing(client, ("USD", "BYN"))
    assert result == ["P-1", "P-2", "P-3"]
    assert client._id_by_internal == {}


@pytest.mark.asyncio
async def test_collect_listing_parse_failure_skipped(caplog):
    from scraper.pipeline import collect_listing

    client = FakeClient()

    async def bad_listing(currency):
        return {"items": [{"name": "no id no currency"}]}

    client.fetch_listing = bad_listing
    result = await collect_listing(client, ("USD",))
    assert result == []


@pytest.mark.asyncio
async def test_collect_listing_parser_raises_skipped(monkeypatch, caplog):
    from scraper.pipeline import collect_listing

    client = FakeClient()

    def bad_parse(payload, currency):
        raise ScraperError("parser exploded")

    monkeypatch.setattr("scraper.api.listing.parse_listing_payload", bad_parse)
    result = await collect_listing(client, ("USD",))
    assert result == []


# ------------------------------------------------------------ collect_details ---


@pytest.mark.asyncio
async def test_collect_details_mixed_statuses(caplog):
    from scraper.pipeline import collect_details

    client = FakeClient(settings=SimpleNamespace(max_concurrency=1))
    client.detail_errors = {
        "P-2": NotFoundError("gone"),
        "P-3": TransientError("slow"),
        "P-4": RuntimeError("boom"),
    }
    ok, err = await collect_details(client, ["P-1", "P-2", "P-3", "P-4"], batch_size=2)
    assert ok == 2  # ok + delisted
    assert err == 2
    async with session_scope() as session:
        from sqlalchemy import select

        bonds = (await session.execute(select(BondORM))).scalars().all()
        by_id = {b.internal_id: b for b in bonds}
    assert by_id["P-1"].status == "active"
    assert by_id["P-2"].status == "delisted"
    assert by_id["P-2"].currency == "USD"


@pytest.mark.asyncio
async def test_collect_details_parse_error_status(caplog):
    from scraper.pipeline import collect_details

    client = FakeClient()
    client.detail_errors = {"P-1": ParseError("bad payload")}
    ok, err = await collect_details(client, ["P-1"])
    assert (ok, err) == (0, 1)


# -------------------------------------------------------- _delisted_placeholder ---


@pytest.mark.asyncio
async def test_delisted_placeholder_keeps_known_currency(caplog):
    from scraper.pipeline import _delisted_placeholder

    async with session_scope() as session:
        session.add(
            BondORM(
                internal_id="DP-1",
                name="Old Name",
                currency="BYN",
                market="bcse",
                status="active",
                fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        await session.flush()
    bond = await _delisted_placeholder("DP-1")
    assert (bond.name, bond.currency, bond.status) == ("Old Name", "BYN", "delisted")

    bond2 = await _delisted_placeholder("DP-2")
    assert (bond2.name, bond2.currency) == ("DP-2", "USD")


@pytest.mark.asyncio
async def test_delisted_placeholder_lookup_failure(monkeypatch, caplog):
    from contextlib import asynccontextmanager

    from scraper.pipeline import _delisted_placeholder

    @asynccontextmanager
    async def broken_scope(**kwargs):
        raise RuntimeError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr("scraper.pipeline.session_scope", broken_scope)
    bond = await _delisted_placeholder("DP-X")
    assert (bond.name, bond.currency, bond.status) == ("DP-X", "USD", "delisted")


# ------------------------------------------------------------ backfill_history ---


@pytest.mark.asyncio
async def test_backfill_history_variants(caplog):
    from scraper.pipeline import backfill_history

    async def run(error=None, payload=None, last=None):
        client = FakeClient()
        client.history_error = error
        if payload is not None:
            client.fetch_history = AsyncMock(return_value=payload)
        if last is not None:
            async with session_scope() as session:
                session.add(
                    BondHistoryORM(
                        internal_id="BH-1",
                        date=last,
                        price=Decimal("100"),
                        yield_=Decimal("8"),
                        status="active",
                    )
                )
                await session.flush()
        return await backfill_history(client, ["BH-1"], days=30)

    assert await run(error=HistoryUnavailable("no history")) == (0, 0)
    assert await run(error=NotFoundError("gone")) == (0, 0)
    assert await run(error=TransientError("slow")) == (0, 1)
    assert await run(error=RuntimeError("boom")) == (0, 1)
    assert await run(payload=[]) == (0, 0)
    ok, err = await run(payload=HISTORY_PAYLOAD)
    assert (ok, err) == (2, 0)
    assert await run(payload=HISTORY_PAYLOAD, last=date.today() + timedelta(days=5)) == (0, 0)


# ------------------------------------------------------------- enrich_from_xlsx ---


def _enrichment(**overrides):
    kwargs = {
        "issue_number": 1,
        "name": "Первый выпуск.xlsx",
        "face_value": Decimal("1000"),
        "quantity": 100,
        "issue_volume": Decimal("5000000"),
        "coupon_rate": Decimal("8.5"),
        "start_date": date(2025, 1, 1),
        "maturity_date": date(2030, 1, 1),
        "term_days": 1825,
        "indexation_currency": "USD",
        "coupon_periods": [{"start": "2026-01-15"}, {"start": ""}],
    }
    kwargs.update(overrides)
    return SimpleNamespace(**kwargs)


@pytest.mark.asyncio
async def test_enrich_from_xlsx_download_failure(monkeypatch, caplog):
    from scraper.pipeline import enrich_from_xlsx

    def parse_boom():
        raise RuntimeError("download failed")

    monkeypatch.setattr("scraper.parsers.xlsx.parse_all", parse_boom)
    assert await enrich_from_xlsx() == {"xlsx_bonds_enriched": 0, "xlsx_accruals_written": 0}


@pytest.mark.asyncio
async def test_enrich_from_xlsx_full_flow(monkeypatch):
    from scraper.parsers.xlsx import XlsxParseResult
    from scraper.pipeline import enrich_from_xlsx

    async with session_scope() as session:
        session.add(
            BondORM(
                internal_id="X1",
                name="Старое имя",
                currency="BYN",
                market="bcse",
                status="active",
                issue_number=1,
                fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.add(
            BondORM(
                internal_id="op-17",
                name="Op 17",
                currency="BYN",
                market="bcse",
                status="active",
                issue_number=None,
                fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.add(
            BondORM(
                internal_id="X2",
                name="Bond X2",
                currency="BYN",
                market="bcse",
                status="active",
                issue_number=99,
                fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        await session.flush()

    xlsx = XlsxParseResult(
        byn_bonds={1: _enrichment(), 2: _enrichment(issue_number=2)},
        indexed_bonds={
            "op17": _enrichment(issue_number=None, name="Индексируемый 17.xlsx"),
        },
        daily_accruals=[
            BondDailyAccrual(
                internal_id="1",
                date=date(2026, 1, 2),
                accrued=Decimal("10"),
                total_value=Decimal("1010"),
            ),
            BondDailyAccrual(
                internal_id="abc",
                date=date(2026, 1, 2),
                accrued=Decimal("1"),
                total_value=Decimal("1"),
            ),
            BondDailyAccrual(
                internal_id="77",
                date=date(2026, 1, 2),
                accrued=Decimal("1"),
                total_value=Decimal("1"),
            ),
        ],
    )
    result = await enrich_from_xlsx(xlsx_data=xlsx)
    assert result["xlsx_bonds_enriched"] == 1
    assert result["xlsx_accruals_written"] == 1

    async with session_scope() as session:
        from sqlalchemy import select

        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == "X1"))
        ).scalar_one()
        assert bond.nominal == Decimal("1000")
        assert bond.quantity == 100
        assert bond.issue_volume == Decimal("5000000")
        assert bond.coupon_rate == Decimal("8.5")
        assert bond.start_date == date(2025, 1, 1)
        assert bond.end_date == date(2030, 1, 1)
        assert bond.term_days == 1825
        assert bond.indexation_currency == "USD"
        assert bond.name == "Первый выпуск"
        assert bond.coupon_schedule == {"2026": ["2026-01-15"]}
        renamed = (
            await session.execute(select(BondORM).where(BondORM.internal_id == "op-17"))
        ).scalar_one()
        assert renamed.name == "Индексируемый 17.xlsx"


# -------------------------------------------------------------- run_once_moex ---


@pytest.mark.asyncio
async def test_run_once_moex_requires_moex_client():
    from scraper.pipeline import run_once_moex

    with pytest.raises(TypeError):
        await run_once_moex(SimpleNamespace(), ["USD"])


@pytest.mark.asyncio
async def test_run_once_moex_full_flow(monkeypatch, caplog):
    from scraper.config import get_settings
    from scraper.moex import MoexClient
    from scraper.pipeline import run_once_moex

    monkeypatch.setenv("MOEX_HISTORY_SAMPLE", "2")
    settings = get_settings()
    client = MoexClient(settings)
    client.fetch_bonds = AsyncMock(
        side_effect=[
            [],  # RUB → moex_no_bonds
            [
                Bond(
                    internal_id="M-1",
                    name="Bond M1",
                    currency="CNY",
                    status="active",
                    fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            ],
        ]
    )
    client.fetch_history = AsyncMock(
        return_value=[
            BondHistory(
                internal_id="M-1",
                date=date(2026, 1, 2),
                price=Decimal("101"),
                yield_=Decimal("8"),
                status="active",
            )
        ]
    )
    client.fetch_coupons = AsyncMock(return_value=[{"date": date(2026, 1, 15)}])
    monkeypatch.setattr(
        "scraper.pipeline.enrich_from_xlsx",
        AsyncMock(return_value={"xlsx_bonds_enriched": 0, "xlsx_accruals_written": 0}),
    )
    monkeypatch.setattr("scraper.pipeline.recompute_all", AsyncMock(return_value=5))

    summary = await run_once_moex(client, ["CNY"])
    assert summary["listing_total"] == 1
    assert summary["history_rows"] == 1
    assert summary["coupon_bonds"] == 1
    assert summary["scored"] == 5
    assert summary["moex_mode"] is True
    assert summary["history_err"] == 0

    async with session_scope() as session:
        from sqlalchemy import select

        orm = (
            await session.execute(select(BondORM).where(BondORM.internal_id == "M-1"))
        ).scalar_one()
        assert orm.market == "bcse"


@pytest.mark.asyncio
async def test_run_once_moex_updates_existing_and_counts_errors(monkeypatch, caplog):
    from scraper.config import get_settings
    from scraper.moex import MoexClient
    from scraper.pipeline import run_once_moex

    monkeypatch.setenv("MOEX_HISTORY_SAMPLE", "2")
    from sqlalchemy import delete

    async with session_scope() as session:
        await session.execute(delete(BondORM))
        session.add(
            BondORM(
                internal_id="M-2",
                name="Old",
                currency="CNY",
                market="bcse",
                status="active",
                fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        await session.flush()

    client = MoexClient(get_settings())
    client.fetch_bonds = AsyncMock(
        side_effect=[
            [],  # RUB → moex_no_bonds
            [
                Bond(
                    internal_id="M-2",
                    name="New",
                    currency="CNY",
                    status="active",
                    fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            ],
        ]
    )

    async def boom_history(iid, _days=30):
        raise RuntimeError("history down")

    client.fetch_history = boom_history
    client.fetch_coupons = AsyncMock(side_effect=RuntimeError("coupons down"))
    monkeypatch.setattr(
        "scraper.pipeline.enrich_from_xlsx",
        AsyncMock(return_value={"xlsx_bonds_enriched": 0, "xlsx_accruals_written": 0}),
    )
    monkeypatch.setattr("scraper.pipeline.recompute_all", AsyncMock(return_value=0))

    summary = await run_once_moex(client, ["CNY"])
    assert summary["history_err"] == 1
    assert summary["coupon_err"] == 1
    async with session_scope() as session:
        from sqlalchemy import select

        orm = (
            await session.execute(select(BondORM).where(BondORM.internal_id == "M-2"))
        ).scalar_one()
        assert orm.name == "New"


def test_build_coupon_schedule():
    from scraper.pipeline import _build_coupon_schedule

    coupons = [
        {"date": date(2026, 3, 1)},
        {"date": None},
        {"coupon": Decimal("4")},
        {"date": date(2026, 1, 15)},
    ]
    assert _build_coupon_schedule(coupons) == {"2026": ["2026-01-15", "2026-03-01"]}


# --------------------------------------------------------- run_once_moex_stocks ---


@pytest.mark.asyncio
async def test_run_once_moex_stocks_disabled(monkeypatch):
    from scraper.pipeline import run_once_moex_stocks

    settings = SimpleNamespace(stock=SimpleNamespace(enabled=False, error_budget=3))
    monkeypatch.setattr("scraper.config.get_settings", lambda: settings)
    assert await run_once_moex_stocks() == {
        "stocks_saved": 0,
        "history_rows": 0,
        "history_err": 0,
        "skipped": 1,
    }


@pytest.mark.asyncio
async def test_run_once_moex_stocks_fetch_failure(monkeypatch, caplog):
    from scraper.pipeline import _reset_stock_failures, run_once_moex_stocks

    _reset_stock_failures()

    async def fetch_boom(self):
        raise RuntimeError("moex down")

    monkeypatch.setattr("scraper.moex_stocks.MoexStockClient.fetch_stocks", fetch_boom)
    summary = await run_once_moex_stocks()
    assert summary["fetch_failed"] == 1


@pytest.mark.asyncio
async def test_run_once_moex_stocks_no_stocks(monkeypatch, caplog):
    from scraper.pipeline import _reset_stock_failures, run_once_moex_stocks

    _reset_stock_failures()
    monkeypatch.setattr(
        "scraper.moex_stocks.MoexStockClient.fetch_stocks",
        AsyncMock(return_value=[]),
    )
    summary = await run_once_moex_stocks(boards=["TQBR"])
    assert summary["fetch_failed"] == 1


@pytest.mark.asyncio
async def test_run_once_moex_stocks_error_budget_exceeded(monkeypatch, caplog):
    from scraper.pipeline import _reset_stock_failures, run_once_moex_stocks

    _reset_stock_failures()
    settings = SimpleNamespace(stock=SimpleNamespace(enabled=True, error_budget=0, boards=["TQBR"]))
    monkeypatch.setattr("scraper.config.get_settings", lambda: settings)

    async def fetch_boom(self, board=None):
        raise RuntimeError("moex down")

    monkeypatch.setattr("scraper.moex_stocks.MoexStockClient.fetch_stocks", fetch_boom)
    summary = await run_once_moex_stocks()
    assert summary["fetch_failed"] == 1


@pytest.mark.asyncio
async def test_run_once_moex_stocks_full_flow(monkeypatch, caplog):
    from scraper.pipeline import _reset_stock_failures, run_once_moex_stocks

    _reset_stock_failures()
    monkeypatch.setenv("MOEX_STOCK_HISTORY_SAMPLE", "2")
    from sqlalchemy import delete

    async with session_scope() as session:
        await session.execute(delete(StockORM))
        await session.commit()
    stock = Stock(
        internal_id="MOEX_SBER",
        secid="SBER",
        name="Sber",
        currency="RUB",
        price=Decimal("300"),
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    fresh = StockHistory(
        internal_id="MOEX_SBER",
        date=date.today(),
        price=Decimal("301"),
        close_price=Decimal("301"),
        status="active",
    )
    stale = StockHistory(
        internal_id="MOEX_SBER",
        date=date(2020, 1, 1),
        price=Decimal("200"),
        close_price=Decimal("200"),
        status="active",
    )

    async def fetch_stocks(self, board=None):
        return [stock]

    async def fetch_history(self, internal_id, _days=30):
        return [fresh, stale]

    monkeypatch.setattr("scraper.moex_stocks.MoexStockClient.fetch_stocks", fetch_stocks)
    monkeypatch.setattr("scraper.moex_stocks.MoexStockClient.fetch_stock_history", fetch_history)

    summary = await run_once_moex_stocks()
    assert summary["stocks_saved"] == 1
    assert summary["history_rows"] == 1  # stale filtered out
    assert summary["moex_stocks_mode"] is True

    async with session_scope() as session:
        from sqlalchemy import select

        orm = (
            await session.execute(select(StockORM).where(StockORM.internal_id == "MOEX_SBER"))
        ).scalar_one()
        assert orm.name == "Sber"


@pytest.mark.asyncio
async def test_run_once_moex_stocks_history_error(monkeypatch, caplog):
    from sqlalchemy import delete

    from scraper.pipeline import _reset_stock_failures, run_once_moex_stocks

    _reset_stock_failures()
    async with session_scope() as session:
        await session.execute(delete(StockORM))
        await session.commit()
    stock = Stock(
        internal_id="MOEX_GAZP",
        secid="GAZP",
        name="Gazprom",
        currency="RUB",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    async def fetch_stocks(self, board=None):
        return [stock]

    async def fetch_history(self, internal_id, _days=30):
        raise RuntimeError("history down")

    monkeypatch.setattr("scraper.moex_stocks.MoexStockClient.fetch_stocks", fetch_stocks)
    monkeypatch.setattr("scraper.moex_stocks.MoexStockClient.fetch_stock_history", fetch_history)
    summary = await run_once_moex_stocks()
    assert summary["history_err"] == 1


# ------------------------------------------------------------------- run_once ---


@pytest.mark.asyncio
async def test_run_once_happy_path(monkeypatch, caplog):
    from scraper.pipeline import run_once

    client = FakeClient()
    client.detail_errors["P-3"] = TransientError("slow detail")

    xlsx_stats = {"xlsx_bonds_enriched": 0, "xlsx_accruals_written": 0}
    monkeypatch.setattr("scraper.pipeline.enrich_from_xlsx", AsyncMock(return_value=xlsx_stats))
    monkeypatch.setattr("scraper.pipeline.recompute_all", AsyncMock(return_value=7))

    summary = await run_once(client, CURRENCIES)
    assert summary["listing_total"] == 3
    assert summary["details_ok"] == 2
    assert summary["details_err"] == 1
    assert summary["history_rows"] == 6
    assert summary["scored"] == 7

    async with session_scope() as session:
        from sqlalchemy import select

        orm = (
            await session.execute(select(BondORM).where(BondORM.internal_id == "P-1"))
        ).scalar_one()
        assert orm.status == "active"


@pytest.mark.asyncio
async def test_run_once_stale_fallback(monkeypatch, caplog):
    from scraper.pipeline import run_once

    class BrokenClient(FakeClient):
        async def fetch_listing(self, currency):
            raise RuntimeError("source down")

    client = BrokenClient()
    monkeypatch.setattr(
        "scraper.pipeline.collect_listing",
        AsyncMock(side_effect=RuntimeError("source down")),
    )

    async def fallback(currency):
        if currency == "USD":
            return [
                {
                    "internal_id": "FB-1",
                    "name": "FB One",
                    "currency": "USD",
                    "price": "101",
                    "yield_to_maturity": "8.2",
                    "maturity_date": "2030-01-01",
                },
                {
                    "internal_id": "FB-1",
                    "name": "FB One",
                    "currency": "USD",
                    "price": "102",
                    "yield_to_maturity": "8.0",
                    "maturity_date": "not-a-date",
                },
                {"name": "no id", "currency": "USD"},
            ]
        return []

    monkeypatch.setattr("scraper.fallback_source.fetch_fallback_bonds", fallback)
    xlsx_stats = {"xlsx_bonds_enriched": 0, "xlsx_accruals_written": 0}
    monkeypatch.setattr("scraper.pipeline.enrich_from_xlsx", AsyncMock(return_value=xlsx_stats))
    monkeypatch.setattr("scraper.pipeline.recompute_all", AsyncMock(return_value=3))

    summary = await run_once(client, CURRENCIES)
    assert summary["stale_mode"] is True
    assert summary["scored"] == 3

    async with session_scope() as session:
        from sqlalchemy import select

        orm = (
            await session.execute(select(BondORM).where(BondORM.internal_id == "FB-1"))
        ).scalar_one()
        assert orm.price == Decimal("102")
        assert orm.maturity_date == date(2030, 1, 1)
