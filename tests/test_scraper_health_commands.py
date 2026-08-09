"""Tests for scraper/health.py, scraper/commands.py and scraper/validation.py."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from scraper import health, validation
from scraper.errors import ValidationError as ScraperValidationError


class FakeScope:
    def __init__(self):
        self.session = MagicMock()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


class _Result:
    def __init__(self, by_kind):
        self.by_kind = by_kind


class TestHealth:
    async def test_ok(self, capsys, monkeypatch):
        monkeypatch.setattr("scraper.repositories.bonds.count_bonds", AsyncMock(return_value=3))
        monkeypatch.setattr("scraper.repositories.history.count_history", AsyncMock(return_value=10))
        latest = MagicMock()
        latest.isoformat.return_value = "2026-06-01T10:00:00"
        monkeypatch.setattr(
            "scraper.repositories.bonds.latest_fetched_at", AsyncMock(return_value=latest)
        )
        monkeypatch.setattr("scraper.db.session_scope", FakeScope)
        assert await health.health() == 0
        out = capsys.readouterr().out
        assert '"status": "ok"' in out
        assert '"bonds_total": 3' in out
        assert '"last_fetched_at": "2026-06-01T10:00:00"' in out

    async def test_empty(self, capsys, monkeypatch):
        monkeypatch.setattr("scraper.repositories.bonds.count_bonds", AsyncMock(return_value=0))
        monkeypatch.setattr("scraper.repositories.history.count_history", AsyncMock(return_value=0))
        monkeypatch.setattr(
            "scraper.repositories.bonds.latest_fetched_at", AsyncMock(return_value=None)
        )
        monkeypatch.setattr("scraper.db.session_scope", FakeScope)
        assert await health.health() == 0
        out = capsys.readouterr().out
        assert '"status": "empty"' in out
        assert '"last_fetched_at": null' in out

    async def test_error(self, capsys, monkeypatch):
        async def boom(session):
            raise RuntimeError("db down")

        monkeypatch.setattr("scraper.repositories.bonds.count_bonds", boom)
        monkeypatch.setattr("scraper.db.session_scope", FakeScope)
        assert await health.health() == 1
        out = capsys.readouterr().out
        assert '"status": "error"' in out
        assert "db down" in out

    def test_main_exits_with_code(self, monkeypatch):
        def fake_run(coro):
            coro.close()
            return 0

        monkeypatch.setattr("scraper.health.asyncio_run", fake_run)
        with pytest.raises(SystemExit) as exc:
            health.main()
        assert exc.value.code == 0

    def test_main_exits_nonzero(self, monkeypatch):
        def fake_run(coro):
            coro.close()
            return 1

        monkeypatch.setattr("scraper.health.asyncio_run", fake_run)
        with pytest.raises(SystemExit) as exc:
            health.main()
        assert exc.value.code == 1

    def test_asyncio_run(self):
        import asyncio

        assert health.asyncio_run(asyncio.sleep(0, result=42)) == 42

    def test_main_guard_subprocess(self):
        import os
        import subprocess
        import sys

        env = {
            **os.environ,
            "DATABASE_URL": "postgresql+asyncpg://user:pass@127.0.0.1:1/none",
        }
        proc = subprocess.run(
            [sys.executable, "-m", "scraper.health"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        assert proc.returncode == 1
        assert '"status": "error"' in proc.stdout


class TestCommands:
    async def test_cmd_score(self, capsys, monkeypatch):
        monkeypatch.setattr("scraper.commands.recompute_all", AsyncMock(return_value=7))
        monkeypatch.setattr("scraper.db.session_scope", FakeScope)
        from scraper.commands import cmd_score

        assert await cmd_score() == 0
        assert "7 bonds" in capsys.readouterr().out

    async def test_cmd_monitor(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "scraper.commands.detect_bond_changes", AsyncMock(return_value=_Result({"up": 1}))
        )
        monkeypatch.setattr(
            "scraper.commands.detect_fx_changes", AsyncMock(return_value=_Result({"down": 2}))
        )
        monkeypatch.setattr(
            "scraper.commands.detect_metal_changes", AsyncMock(return_value=_Result({"up": 3}))
        )
        monkeypatch.setattr("scraper.db.session_scope", FakeScope)
        from scraper.commands import cmd_monitor

        assert await cmd_monitor() == 0
        out = capsys.readouterr().out
        assert "'bonds': {'up': 1}" in out
        assert "'fx': {'down': 2}" in out
        assert "'metals': {'up': 3}" in out

    def test_main_score(self, monkeypatch):
        from scraper.commands import main_score

        monkeypatch.setattr("scraper.commands.recompute_all", AsyncMock(return_value=7))
        monkeypatch.setattr("scraper.db.session_scope", FakeScope)
        assert main_score() == 0

    def test_main_monitor(self, monkeypatch):
        from scraper.commands import main_monitor

        monkeypatch.setattr(
            "scraper.commands.detect_bond_changes", AsyncMock(return_value=_Result({"up": 1}))
        )
        monkeypatch.setattr(
            "scraper.commands.detect_fx_changes", AsyncMock(return_value=_Result({"down": 2}))
        )
        monkeypatch.setattr(
            "scraper.commands.detect_metal_changes", AsyncMock(return_value=_Result({"up": 3}))
        )
        monkeypatch.setattr("scraper.db.session_scope", FakeScope)
        assert main_monitor() == 0


class TestValidateDetail:
    def test_valid(self):
        data = {"id": "OP-1", "name": "X", "currency": "BYN", "price": "100.5"}
        assert validation.validate_detail(data) is data

    def test_missing_required(self):
        with pytest.raises(ScraperValidationError) as exc:
            validation.validate_detail({"id": "OP-1"})
        assert "name" in str(exc.value)
        assert exc.value.context == {"missing": ["name", "currency"]} or exc.value.context == {
            "missing": ["currency", "name"]
        }

    def test_missing_id(self):
        with pytest.raises(ScraperValidationError) as exc:
            validation.validate_detail({"name": "X", "currency": "BYN"})
        assert "id or internal_id" in str(exc.value)

    def test_bad_ytm(self):
        with pytest.raises(ScraperValidationError) as exc:
            validation.validate_detail({"id": "OP-1", "name": "X", "currency": "BYN", "yield_to_maturity": "abc"})
        assert "yield_to_maturity" in str(exc.value)
        assert exc.value.__cause__ is not None

    def test_bad_price(self):
        with pytest.raises(ScraperValidationError):
            validation.validate_detail({"id": "OP-1", "name": "X", "currency": "BYN", "price": "x"})

    def test_none_price_ok(self):
        data = {"id": "OP-1", "name": "X", "currency": "BYN", "price": None}
        assert validation.validate_detail(data) is data


class TestValidateListing:
    def test_valid_item(self):
        item = {"internal_id": "OP-1", "name": "X", "currency": "BYN"}
        assert validation.validate_listing_item(item) is item

    def test_missing_field(self):
        with pytest.raises(ScraperValidationError) as exc:
            validation.validate_listing_item({"internal_id": "OP-1", "name": "X"})
        assert "currency" in str(exc.value)

    def test_validate_listing(self):
        good = {"internal_id": "OP-1", "name": "X", "currency": "BYN"}
        good2 = {"internal_id": "OP-2", "name": "Y", "currency": "USD"}
        out = validation.validate_listing([good, good2])
        assert out == [good, good2]

    def test_validate_listing_raises(self):
        with pytest.raises(ScraperValidationError):
            validation.validate_listing(
                [{"internal_id": "OP-2", "name": "Y"}]
            )
