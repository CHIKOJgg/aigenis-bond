"""Tests for scraper.providers.*, scraper.fx, remaining instrument_map/lineage branches."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from scraper.db import session_scope
from scraper.instrument_map import (
    InstrumentMapping,
    add_mapping,
    get_mapping_stats,
    list_mappings_db,
    load_mappings,
    resolve_aigenis_id,
    resolve_aigenis_id_db,
    resolve_isin,
    resolve_isin_db,
    upsert_mapping_db,
)
from scraper.lineage import latest_lineage, record_snapshot_lineage


# ──────────────────────────────────────────────
# scraper.providers
# ──────────────────────────────────────────────


class _StubProvider:
    async def fetch_bonds(self, market):
        if market == "bcse":
            raise RuntimeError("boom")
        return [{"internal_id": "M1"}]

    async def health_check(self):
        return True


@pytest.mark.asyncio
async def test_fetch_bonds_all_markets_isolates_errors():
    from scraper.providers import MarketDataProvider

    class Stub(_StubProvider, MarketDataProvider):
        @property
        def data_lineage(self):
            return object()

    result = await Stub().fetch_bonds_all_markets()
    assert result == {"bcse": [], "moex": [{"internal_id": "M1"}]}


def test_data_lineage_to_dict():
    from datetime import UTC, datetime

    from scraper.providers import DataLineage

    dl = DataLineage(source="test", license_contract_id="L1", as_of=datetime(2026, 1, 2, 3, 4, tzinfo=UTC))
    out = dl.to_dict()
    assert out["source"] == "test"
    assert out["license_contract_id"] == "L1"
    assert out["as_of"] == "2026-01-02T03:04:00+00:00"
    assert out["quality_status"] == "ok"
    assert out["ingestion_run"] is None


def test_provider_abstract_members():
    from scraper.providers import MarketDataProvider

    assert MarketDataProvider.__abstractmethods__ == {
        "data_lineage",
        "fetch_bonds",
        "health_check",
    }


def test_registry_get_provider_known_names():
    from scraper.providers.registry import get_provider

    from scraper.providers.aigenis_official import AigenisOfficialProvider
    from scraper.providers.demo import DemoFixtureProvider
    from scraper.providers.moex import MoexProvider

    assert isinstance(get_provider("moex"), MoexProvider)
    assert isinstance(get_provider("moex_iss"), MoexProvider)
    assert isinstance(get_provider("demo"), DemoFixtureProvider)
    assert isinstance(get_provider("demo_fixtures"), DemoFixtureProvider)
    assert isinstance(get_provider("aigenis_official"), AigenisOfficialProvider)


def test_registry_get_provider_unknown_raises():
    from scraper.providers.registry import ProviderNotConfiguredError, get_provider

    with pytest.raises(ProviderNotConfiguredError):
        get_provider("nonexistent")


def test_registry_default_profile_default_env(monkeypatch):
    from scraper.providers.registry import _default_provider_name

    monkeypatch.delenv("DEPLOYMENT_PROFILE", raising=False)
    assert _default_provider_name() == "moex"


def test_fail_closed_with_both_sources(monkeypatch):
    from scraper.providers.registry import ProviderNotConfiguredError, assert_browser_scraping_allowed

    monkeypatch.setenv("DEPLOYMENT_PROFILE", "aigenis")
    monkeypatch.setenv("DATA_SOURCE", "both")
    with pytest.raises(ProviderNotConfiguredError):
        assert_browser_scraping_allowed()


@pytest.mark.asyncio
async def test_moex_provider_active():
    from scraper.providers.moex import MoexProvider

    provider = MoexProvider(active=True)
    assert await provider.fetch_bonds("moex") == []
    assert await provider.health_check() is True
    assert provider.data_lineage.source == "moex_iss"
    assert provider.data_lineage.license_contract_id == "public"


@pytest.mark.asyncio
async def test_aigenis_official_active():
    from scraper.providers.aigenis_official import AigenisOfficialProvider

    provider = AigenisOfficialProvider(api_url="https://api.example", api_key="k")
    assert await provider.fetch_bonds("bcse") == []
    assert await provider.health_check() is False
    assert provider.data_lineage.source == "aigenis_official"
    assert provider.data_lineage.license_contract_id == "pending"


@pytest.mark.asyncio
async def test_demo_provider_custom_fixtures():
    from scraper.providers.demo import DemoFixtureProvider

    fixture = {
        "internal_id": "X1",
        "market": "moex",
        "name": "Test",
    }
    provider = DemoFixtureProvider(fixtures=[fixture])
    assert await provider.fetch_bonds("moex") == [fixture]
    assert await provider.fetch_bonds("bcse") == []
    assert provider.data_lineage.source == "demo_fixtures"
    assert await provider.health_check() is True


def test_demo_default_fixtures_shallow_copies():
    from scraper.providers.demo import default_fixtures

    first = default_fixtures()
    second = default_fixtures()
    assert len(first) == 5
    assert first is not second
    assert first[0] is not second[0]
    assert {b["market"] for b in first} == {"bcse", "moex"}
    assert {b["currency"] for b in first} == {"BYN", "RUB"}
    assert all(b["is_government"] is False for b in first if b["issuer"] not in ("Минфин РБ", "Минфин РФ"))


# ──────────────────────────────────────────────
# scraper.instrument_map — remaining branches
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_mappings_db_with_and_without_market():
    async with session_scope() as session:
        await upsert_mapping_db(
            session,
            InstrumentMapping(aigenis_instrument_id="L-BCSE", market="BCSE", analytics_internal_id="b1"),
        )
        await upsert_mapping_db(
            session,
            InstrumentMapping(aigenis_instrument_id="L-MOEX", market="MOEX", analytics_internal_id="b2"),
        )

    async with session_scope() as session:
        all_rows = await list_mappings_db(session)
        ids = {r.aigenis_instrument_id for r in all_rows}
        assert {"L-BCSE", "L-MOEX"} <= ids
        moex_only = await list_mappings_db(session, market="MOEX")
        assert all(r.market == "MOEX" for r in moex_only)
        assert {r.aigenis_instrument_id for r in moex_only} == {"L-MOEX"}


@pytest.mark.asyncio
async def test_resolve_isin_db_missing():
    async with session_scope() as session:
        assert await resolve_isin_db(session, "BY0000MISSING") is None
        assert await resolve_aigenis_id_db(session, "NOPE") is None


def test_in_memory_mapping_api():
    load_mappings(
        [
            InstrumentMapping(aigenis_instrument_id="IM-1", isin="BY1000000001", status="active"),
            InstrumentMapping(aigenis_instrument_id="IM-2", isin="BY1000000002", status="delisted"),
        ]
    )

    found = resolve_aigenis_id("IM-1")
    assert found.isin == "BY1000000001"
    assert found.status == "active"

    uncovered = resolve_aigenis_id("UNKNOWN")
    assert uncovered.status.value == "not_covered"
    assert uncovered.aigenis_instrument_id == "UNKNOWN"

    by_isin = resolve_isin("BY1000000002")
    assert by_isin is not None and by_isin.aigenis_instrument_id == "IM-2"
    assert resolve_isin("BY9999999999") is None

    stats = get_mapping_stats()
    assert stats.get("active") == 1
    assert stats.get("delisted") == 1

    add_mapping(InstrumentMapping(aigenis_instrument_id="IM-3", status="renamed"))
    assert resolve_aigenis_id("IM-3").status.value == "renamed"
    stats = get_mapping_stats()
    assert stats.get("renamed") == 1


# ──────────────────────────────────────────────
# scraper.lineage — remaining branches
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_lineage_with_extra_and_latest_empty():
    from sqlalchemy import delete

    from scraper.orm import SnapshotLineageORM

    async with session_scope() as session:
        await session.execute(delete(SnapshotLineageORM))
        await session.flush()
        assert await latest_lineage(session) is None
        row = await record_snapshot_lineage(
            session,
            source="extra_source",
            extra={"rows": 7},
        )
        assert row.source == "extra_source"
        latest = await latest_lineage(session)
        assert latest is not None and latest.source == "extra_source"


# ──────────────────────────────────────────────
# scraper.fx
# ──────────────────────────────────────────────


class FakeResponse:
    def __init__(self, json_data=None, text="", ok=True):
        self._json = json_data
        self._text = text
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("HTTP error")
        return None

    def json(self):
        return self._json

    @property
    def text(self):
        return self._text


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        self.requests.append(("get", url))
        return FakeResponse(json_data=self._get_body(url))

    async def post(self, url, **kwargs):
        self.requests.append(("post", url, kwargs))
        return FakeResponse(text=self._post_body(kwargs.get("content", "")))

    def _get_body(self, url):
        raise NotImplementedError

    def _post_body(self, content):
        raise NotImplementedError


class RatesFakeClient(FakeClient):
    def _get_body(self, url):
        return [
            {"Cur_Abbreviation": "USD", "Cur_Scale": 1, "Cur_OfficialRate": "3.2"},
            {"Cur_Abbreviation": "EUR", "Cur_Scale": 1, "Cur_OfficialRate": None},
            {"Cur_Abbreviation": "RUB", "Cur_Scale": 100, "Cur_OfficialRate": "340.5"},
            {"Cur_Abbreviation": "JPY", "Cur_Scale": 100, "Cur_OfficialRate": "2.0"},
        ]


@pytest.mark.asyncio
async def test_fetch_and_save_rates(monkeypatch):
    from scraper.fx import fetch_and_save_rates
    from notifications.fx_repository import latest_fx

    client = RatesFakeClient()
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    rates = await fetch_and_save_rates()
    assert rates == {"USD/BYN": Decimal("3.2"), "RUB/BYN": Decimal("3.405")}
    assert client.requests[0][0] == "get"

    async with session_scope() as session:
        usd = await latest_fx(session, "USD/BYN")
        assert usd is not None and usd.rate == Decimal("3.2")
        assert await latest_fx(session, "EUR/BYN") is None


def test_build_soap_envelope():
    from scraper.fx import _build_soap_envelope

    envelope = _build_soap_envelope(0, date(2026, 1, 1), date(2026, 1, 8))
    assert "<MetalId>0</MetalId>" in envelope
    assert "<fromDate>2026-01-01</fromDate>" in envelope
    assert "<toDate>2026-01-08</toDate>" in envelope


def test_parse_metal_prices():
    from scraper.fx import _parse_metal_prices

    xml = """<?xml version='1.0'?>
<soap:Envelope xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'>
  <soap:Body>
    <MetalsPrices xmlns='https://www.nbrb.by/'>
      <AccountPrice>
        <Price>1.2345</Price>
      </AccountPrice>
      <AccountPrice>
        <Price/>
      </AccountPrice>
    </MetalsPrices>
  </soap:Body>
</soap:Envelope>"""
    assert _parse_metal_prices(xml) == [Decimal("1.2345")]

    plain = "<root><AccountPrice><Price>9.99</Price></AccountPrice></root>"
    assert _parse_metal_prices(plain) == [Decimal("9.99")]


class SoapFakeClient(FakeClient):
    def _post_body(self, content):
        return (
            "<?xml version='1.0'?><MetalsPrices>"
            "<AccountPrice><Price>1.5</Price></AccountPrice>"
            "</MetalsPrices>"
        )


@pytest.mark.asyncio
async def test_fetch_metal_prices_soap(monkeypatch):
    from scraper.fx import _fetch_metal_prices_soap

    client = SoapFakeClient()
    monkeypatch.setattr("httpx.AsyncClient", lambda **kw: client)

    prices = await _fetch_metal_prices_soap(0, date(2026, 1, 1), date(2026, 1, 8))
    assert prices == [Decimal("1.5")]
    method, url, kwargs = client.requests[0]
    assert method == "post"
    assert url.endswith("exrates.asmx")
    assert kwargs["headers"]["SOAPAction"].endswith("MetalsPrices")


@pytest.mark.asyncio
async def test_fetch_and_save_metal_prices(monkeypatch):
    from scraper.fx import TROY_OZ_PER_GRAM, fetch_and_save_metal_prices
    from notifications.fx_repository import latest_metal

    async def fake_fetch(metal_id, from_date, to_date):
        return [] if metal_id == 1 else [Decimal("1.5")]

    monkeypatch.setattr("scraper.fx._fetch_metal_prices_soap", fake_fetch)

    metals = await fetch_and_save_metal_prices()
    assert "XAU" in metals and "XPT" in metals
    assert "XAG" not in metals
    assert metals["XAU"] == Decimal("1.5") * TROY_OZ_PER_GRAM

    async with session_scope() as session:
        xau = await latest_metal(session, "XAU")
        assert xau is not None and xau.price == Decimal("46.655215")
        assert await latest_metal(session, "XAG") is None


class FakeAigenisClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_fetch_and_save_bonds(monkeypatch):
    from scraper.fx import fetch_and_save_bonds

    run_once = AsyncMock(return_value={"fetched": 3})
    monkeypatch.setattr("scraper.client.AigenisClient", FakeAigenisClient)
    monkeypatch.setattr("scraper.pipeline.run_once", run_once)

    summary = await fetch_and_save_bonds()
    assert summary == {"fetched": 3}
    run_once.assert_awaited_once()
