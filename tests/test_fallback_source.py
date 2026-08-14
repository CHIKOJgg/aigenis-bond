"""Tests for scraper/fallback_source.py (MOEX ISS fallback quote adapter)."""

from __future__ import annotations

import httpx
import pytest

import scraper.fallback_source as fb


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _url_key(url: str) -> tuple[str, int]:
    board = url.split("boards/")[1].split("/")[0]
    start = int(url.split("iss.start=")[1].split("&")[0])
    return (board, start)


class FakeMoexClient:
    def __init__(self, pages, enter_error=None):
        self.pages = pages
        self.calls: list[str] = []
        self.enter_error = enter_error

    async def get(self, url):
        self.calls.append(url)
        key = _url_key(url)
        if key not in self.pages:
            raise httpx.ConnectError("no page for request")
        return FakeResp(self.pages[key])

    async def __aenter__(self):
        if self.enter_error:
            raise self.enter_error
        return self

    async def __aexit__(self, *args):
        return False


def _securities_payload(rows: list[dict], start: int = 0):
    return {
        "securities": {
            "columns": ["SECID", "SECNAME", "FACEUNIT", "MATDATE", "ISSUER", "SHORTNAME"],
            "data": [
                [
                    r.get("SECID"),
                    r.get("SECNAME"),
                    r.get("FACEUNIT"),
                    r.get("MATDATE"),
                    r.get("ISSUER"),
                    r.get("SHORTNAME"),
                ]
                for r in rows
            ],
        },
        "marketdata": {
            "columns": ["SECID", "LAST", "YIELD"],
            "data": [[r["SECID"], r.get("LAST"), r.get("YIELD")] for r in rows if r.get("SECID")],
        },
    }


def _row(secid="MOEX1", currency="RUB", last="100.5", ytm="7.25", matdate="2030-05-01"):
    return {
        "SECID": secid,
        "SECNAME": f"Bond {secid}",
        "FACEUNIT": currency,
        "MATDATE": matdate,
        "ISSUER": None,
        "SHORTNAME": "Short",
        "LAST": last,
        "YIELD": ytm,
    }


@pytest.fixture(autouse=True)
def clean_module_state(monkeypatch):
    monkeypatch.setattr(fb, "_FALLBACK_SOURCE", "moex")
    monkeypatch.setattr(fb, "_MOEX_BOARDS", ["TQCB", "TQOB"])
    monkeypatch.setattr(fb, "_MOEX_CAP", 1000)
    monkeypatch.setattr(fb.logger, "warning", lambda *a, **k: None)
    monkeypatch.setattr(fb.logger, "info", lambda *a, **k: None)


class TestFetchFallbackBonds:
    @pytest.mark.asyncio
    async def test_no_source(self, monkeypatch):
        monkeypatch.setattr(fb, "_FALLBACK_SOURCE", "")
        assert await fb.fetch_fallback_bonds("USD") == []

    @pytest.mark.asyncio
    async def test_unknown_source(self, monkeypatch):
        monkeypatch.setattr(fb, "_FALLBACK_SOURCE", "bogus")
        assert await fb.fetch_fallback_bonds() == []

    @pytest.mark.asyncio
    async def test_moex_dispatch(self, monkeypatch):
        from unittest.mock import AsyncMock

        fetch = AsyncMock(return_value=[{"internal_id": "MOEX_X"}])
        monkeypatch.setattr(fb, "_fetch_moex_bonds", fetch)
        assert await fb.fetch_fallback_bonds("USD") == [{"internal_id": "MOEX_X"}]
        fetch.assert_awaited_once_with("USD")


class TestParseIssRows:
    def test_missing_node(self):
        assert fb._parse_iss_rows({}, "securities") == []

    def test_ok(self):
        payload = {
            "securities": {
                "columns": ["SECID", "SECNAME"],
                "data": [["X", "Y"], ["A", "B"]],
            }
        }
        assert fb._parse_iss_rows(payload, "securities") == [
            {"SECID": "X", "SECNAME": "Y"},
            {"SECID": "A", "SECNAME": "B"},
        ]


class TestFetchMoexBonds:
    @pytest.mark.asyncio
    async def test_currency_filter(self, monkeypatch):
        page = _securities_payload([_row("RUB1", "RUB"), _row("USD1", "USD", last=None, ytm=None)])
        client = FakeMoexClient({("TQCB", 0): page})
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        rows = await fb._fetch_moex_bonds("USD")
        assert len(rows) == 1
        assert rows[0]["internal_id"] == "MOEX_USD1"
        assert rows[0]["market"] == "moex"
        assert rows[0]["currency"] == "USD"
        assert rows[0]["price"] is None
        assert rows[0]["yield_to_maturity"] is None
        assert rows[0]["maturity_date"] == "2030-05-01"
        assert rows[0]["issuer"] == "Short"
        assert rows[0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_no_currency_filter_keeps_all(self, monkeypatch):
        page = _securities_payload([_row("RUB1", "RUB"), _row("USD1", "USD")])
        client = FakeMoexClient({("TQCB", 0): page})
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        rows = await fb._fetch_moex_bonds(None)
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_prices_and_ytm(self, monkeypatch):
        page = _securities_payload([_row("B1", "RUB", last="101.25", ytm="7.5")])
        client = FakeMoexClient({("TQCB", 0): page})
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        rows = await fb._fetch_moex_bonds()
        assert rows[0]["price"] == 101.25
        assert rows[0]["yield_to_maturity"] == 7.5

    @pytest.mark.asyncio
    async def test_bad_maturity(self, monkeypatch):
        page = _securities_payload([_row("B1", "RUB", matdate="not-a-date")])
        client = FakeMoexClient({("TQCB", 0): page})
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        rows = await fb._fetch_moex_bonds()
        assert rows[0]["maturity_date"] is None

    @pytest.mark.asyncio
    async def test_missing_secid_skipped(self, monkeypatch):
        payload = {
            "securities": {
                "columns": ["SECID", "SECNAME", "FACEUNIT", "MATDATE", "ISSUER", "SHORTNAME"],
                "data": [[None, "NoId", "RUB", None, None, "S"]],
            },
            "marketdata": {"columns": ["SECID", "LAST", "YIELD"], "data": []},
        }
        client = FakeMoexClient({("TQCB", 0): payload})
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        assert await fb._fetch_moex_bonds() == []

    @pytest.mark.asyncio
    async def test_empty_securities_breaks(self, monkeypatch):
        payload = {
            "securities": {"columns": [], "data": []},
            "marketdata": {"columns": [], "data": []},
        }
        client = FakeMoexClient({("TQCB", 0): payload})
        monkeypatch.setattr(fb, "_MOEX_BOARDS", ["TQCB"])
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        assert await fb._fetch_moex_bonds() == []
        assert len(client.calls) == 1

    @pytest.mark.asyncio
    async def test_board_failure(self, monkeypatch):
        client = FakeMoexClient({})
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        assert await fb._fetch_moex_bonds() == []

    @pytest.mark.asyncio
    async def test_cap(self, monkeypatch):
        rows = [_row(f"B{i}", "RUB") for i in range(5)]
        page = _securities_payload(rows)
        client = FakeMoexClient({("TQCB", 0): page})
        monkeypatch.setattr(fb, "_MOEX_BOARDS", ["TQCB"])
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        monkeypatch.setattr(fb, "_MOEX_CAP", 2)
        result = await fb._fetch_moex_bonds()
        assert len(result) == 2
        assert len(client.calls) == 1

    @pytest.mark.asyncio
    async def test_pagination(self, monkeypatch):
        full_rows = [_row(f"B{i}", "RUB") for i in range(100)]
        tail_rows = [_row("TAIL1", "RUB"), _row("TAIL2", "RUB")]
        pages = {
            ("TQCB", 0): _securities_payload(full_rows),
            ("TQCB", 100): _securities_payload(tail_rows),
        }
        client = FakeMoexClient(pages)
        monkeypatch.setattr(fb, "_MOEX_BOARDS", ["TQCB"])
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        result = await fb._fetch_moex_bonds()
        assert len(result) == 102
        assert len(client.calls) == 2
        assert "iss.start=100" in client.calls[1]

    @pytest.mark.asyncio
    async def test_multiple_boards(self, monkeypatch):
        pages = {
            ("TQCB", 0): _securities_payload([_row("RUB1", "RUB")]),
            ("TQOB", 0): _securities_payload([_row("USD1", "USD")]),
        }
        client = FakeMoexClient(pages)
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        monkeypatch.setattr(fb, "_MOEX_BOARDS", ["TQCB", "TQOB"])
        result = await fb._fetch_moex_bonds(None)
        assert len(result) == 2
        assert {r["currency"] for r in result} == {"RUB", "USD"}
        # Регрессия: fallback-адаптер всегда помечает market="moex" (иначе
        # бумаги оседали в BCSE через server_default).
        assert all(r["market"] == "moex" for r in result)

    @pytest.mark.asyncio
    async def test_default_boards_include_usd_eurobonds(self, monkeypatch):
        # Регрессия: по умолчанию fallback сканирует TQCB+RUB и TQOB+USD/EUR,
        # иначе Долларизация/Металлы++ на MOEX не находят инструментов.
        pages = {
            ("TQCB", 0): _securities_payload([_row("R1", "RUB")]),
            ("TQOB", 0): _securities_payload([_row("U1", "USD")]),
        }
        client = FakeMoexClient(pages)
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        monkeypatch.setattr(fb, "_MOEX_BOARDS", ["TQCB", "TQOB"])
        result = await fb._fetch_moex_bonds()
        assert len(result) == 2
        assert {r["currency"] for r in result} == {"RUB", "USD"}

    @pytest.mark.asyncio
    async def test_client_enter_failure(self, monkeypatch):
        client = FakeMoexClient({}, enter_error=RuntimeError("http down"))
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        assert await fb._fetch_moex_bonds() == []

    @pytest.mark.asyncio
    async def test_pagination_bad_maturity_mid(self, monkeypatch):
        full_rows = [_row(f"B{i}", "RUB") for i in range(100)]
        tail_rows = [_row("T1", "RUB", matdate="2031-01-01")]
        pages = {
            ("TQCB", 0): _securities_payload(full_rows),
            ("TQCB", 100): _securities_payload(tail_rows),
        }
        client = FakeMoexClient(pages)
        monkeypatch.setattr(fb.httpx, "AsyncClient", lambda timeout: client)
        result = await fb._fetch_moex_bonds()
        assert result[-1]["maturity_date"] == "2031-01-01"
