"""Tests for scraper/__main__.py (CLI entrypoint) and the legacy parser shims."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import scraper.__main__ as main_mod


class FakeScope:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeClientCM:
    def __init__(self, settings):
        self.settings = settings

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _patch_main_deps(monkeypatch):
    settings = SimpleNamespace(
        aigenis=SimpleNamespace(
            sentry_dsn=None,
            environment="test",
            currencies=["USD", "BYN"],
            history_backfill_days=1825,
        )
    )
    monkeypatch.setattr(main_mod, "configure_logging", lambda: None)
    monkeypatch.setattr(main_mod, "init_sentry", lambda *a, **k: None)
    monkeypatch.setattr(main_mod, "get_settings", lambda: settings)
    return settings


def _patch_command(monkeypatch, name, return_value=0):
    mock = AsyncMock(return_value=return_value)
    monkeypatch.setattr(main_mod, name, mock)
    return mock


class TestCmdOnce:
    @pytest.mark.asyncio
    async def test_all_currencies(self, monkeypatch, capsys):
        settings = _patch_main_deps(monkeypatch)
        monkeypatch.setattr("scraper.client.AigenisClient", FakeClientCM)
        run_once = AsyncMock(return_value={"bonds": 1})
        monkeypatch.setattr(main_mod, "run_once", run_once)
        assert await main_mod._cmd_once("") == 0
        run_once.assert_awaited_once()
        _, currencies = run_once.await_args.args
        assert currencies == settings.aigenis.currencies
        assert "bonds" in capsys.readouterr().out

    @pytest.mark.asyncio
    async def test_explicit_currencies(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        monkeypatch.setattr("scraper.client.AigenisClient", FakeClientCM)
        run_once = AsyncMock(return_value={})
        monkeypatch.setattr(main_mod, "run_once", run_once)
        assert await main_mod._cmd_once("usd, BYN") == 0
        assert run_once.await_args.args[1] == ["USD", "BYN"]


class TestCmdBackfill:
    @pytest.mark.asyncio
    async def test_currency_restricted(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        monkeypatch.setattr("scraper.db.session_scope", FakeScope)
        get_by_currency = AsyncMock(
            return_value=[SimpleNamespace(internal_id="X1"), SimpleNamespace(internal_id="X2")]
        )
        monkeypatch.setattr("scraper.repositories.bonds.get_by_currency", get_by_currency)
        monkeypatch.setattr("scraper.client.AigenisClient", FakeClientCM)
        backfill = AsyncMock(return_value=(5, 2))
        monkeypatch.setattr(main_mod, "backfill_history", backfill)
        assert await main_mod._cmd_backfill("USD", 30) == 0
        get_by_currency.assert_awaited_once()
        assert get_by_currency.await_args.args[1] == "USD"
        backfill.assert_awaited_once()
        ids, days = backfill.await_args.args[1], backfill.await_args.kwargs["days"]
        assert ids == ["X1", "X2"]
        assert days == 30

    @pytest.mark.asyncio
    async def test_all_bonds_default_days(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        monkeypatch.setattr("scraper.db.session_scope", FakeScope)
        monkeypatch.setattr(
            "scraper.repositories.bonds.get_all_internal_ids", AsyncMock(return_value=["A"])
        )
        monkeypatch.setattr("scraper.client.AigenisClient", FakeClientCM)
        backfill = AsyncMock(return_value=(0, 0))
        monkeypatch.setattr(main_mod, "backfill_history", backfill)
        assert await main_mod._cmd_backfill("", None) == 0
        assert backfill.await_args.kwargs["days"] == 1825


class TestCmdRun:
    @pytest.mark.asyncio
    async def test_run(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        run_forever = AsyncMock()
        monkeypatch.setattr("scraper.scheduler.run_forever", run_forever)
        assert await main_mod._cmd_run() == 0
        run_forever.assert_awaited_once()


class TestCmdFx:
    @pytest.mark.asyncio
    async def test_fx_fetch(self, monkeypatch, capsys):
        _patch_main_deps(monkeypatch)
        monkeypatch.setattr(
            "scraper.fx.fetch_and_save_rates", AsyncMock(return_value={"USD/BYN": 2.5})
        )
        assert await main_mod._cmd_fx_fetch() == 0
        assert "USD/BYN: 2.5" in capsys.readouterr().out

    @pytest.mark.asyncio
    async def test_fx_metals(self, monkeypatch, capsys):
        _patch_main_deps(monkeypatch)
        monkeypatch.setattr(
            "scraper.fx.fetch_and_save_metal_prices", AsyncMock(return_value={"XAU": 110.0})
        )
        assert await main_mod._cmd_fx_metals() == 0
        assert "XAU/BYN: 110.0 per troy oz" in capsys.readouterr().out


class TestCmdMoex:
    @pytest.mark.asyncio
    async def test_all_currencies(self, monkeypatch, capsys):
        _patch_main_deps(monkeypatch)
        monkeypatch.setattr("scraper.moex.MoexClient", FakeClientCM)
        run_once_moex = AsyncMock(return_value={"bonds": 3})
        monkeypatch.setattr("scraper.pipeline.run_once_moex", run_once_moex)
        assert await main_mod._cmd_moex("") == 0
        assert run_once_moex.await_args.args[1] == ["USD", "BYN"]
        assert "bonds" in capsys.readouterr().out

    @pytest.mark.asyncio
    async def test_explicit_currencies(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        monkeypatch.setattr("scraper.moex.MoexClient", FakeClientCM)
        run_once_moex = AsyncMock(return_value={})
        monkeypatch.setattr("scraper.pipeline.run_once_moex", run_once_moex)
        assert await main_mod._cmd_moex("RUB,CNY") == 0
        assert run_once_moex.await_args.args[1] == ["RUB", "CNY"]


class TestCmdMoexStocks:
    @pytest.mark.asyncio
    async def test_explicit_boards(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        run = AsyncMock(return_value={})
        monkeypatch.setattr("scraper.pipeline.run_once_moex_stocks", run)
        assert await main_mod._cmd_moex_stocks("tqbr, TQOD") == 0
        assert run.await_args.args[0] == ["TQBR", "TQOD"]

    @pytest.mark.asyncio
    async def test_default_boards(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        run = AsyncMock(return_value={})
        monkeypatch.setattr("scraper.pipeline.run_once_moex_stocks", run)
        assert await main_mod._cmd_moex_stocks("") == 0
        assert run.await_args.args[0] is None


class TestMainDispatch:
    def test_once(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        cmd = _patch_command(monkeypatch, "_cmd_once")
        assert main_mod.main(["once", "--currency", "USD"]) == 0
        cmd.assert_awaited_once_with("USD")

    def test_once_default_currency(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        cmd = _patch_command(monkeypatch, "_cmd_once")
        assert main_mod.main(["once"]) == 0
        cmd.assert_awaited_once_with("")

    def test_backfill(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        cmd = _patch_command(monkeypatch, "_cmd_backfill")
        assert main_mod.main(["backfill", "--days", "10", "--currency", "BYN"]) == 0
        cmd.assert_awaited_once_with("BYN", 10)

    def test_run(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        cmd = _patch_command(monkeypatch, "_cmd_run")
        assert main_mod.main(["run"]) == 0
        cmd.assert_awaited_once()

    def test_health(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        cmd = _patch_command(monkeypatch, "health_cmd")
        assert main_mod.main(["health"]) == 0
        cmd.assert_awaited_once()

    def test_moex(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        cmd = _patch_command(monkeypatch, "_cmd_moex")
        assert main_mod.main(["moex", "--currency", "RUB"]) == 0
        cmd.assert_awaited_once_with("RUB")

    def test_moex_stocks(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        cmd = _patch_command(monkeypatch, "_cmd_moex_stocks")
        assert main_mod.main(["moex-stocks", "--boards", "TQBR"]) == 0
        cmd.assert_awaited_once_with("TQBR")

    def test_score(self, monkeypatch):
        _patch_main_deps(monkeypatch)

        def mock():
            return 0

        monkeypatch.setattr(main_mod, "main_score", mock)
        assert main_mod.main(["score"]) == 0

    def test_monitor(self, monkeypatch):
        _patch_main_deps(monkeypatch)

        def mock():
            return 0

        monkeypatch.setattr(main_mod, "main_monitor", mock)
        assert main_mod.main(["monitor"]) == 0

    def test_ml_commands(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        for command, symbol in [
            ("ml-train", "cmd_ml_train"),
            ("ml-predict", "cmd_ml_predict"),
            ("ml-status", "cmd_ml_status"),
            ("recs", "cmd_recs"),
            ("rebalance-now", "cmd_rebalance_now"),
        ]:
            cmd = _patch_command(monkeypatch, symbol)
            assert main_mod.main([command]) == 0
            cmd.assert_awaited_once()

    def test_desk_commands(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        for command, symbol, args in [
            ("desk-curve", "cmd_desk_curve", ()),
            ("desk-rv", "cmd_desk_rv", ()),
            ("desk-duration", "cmd_desk_duration", ("OP-1",)),
            ("desk-carry", "cmd_desk_carry", (5.0,)),
            ("desk-repo", "cmd_desk_repo", ("OP-2", 1000.0, 30)),
            ("desk-stress", "cmd_desk_stress", ()),
            ("desk-status", "cmd_desk_status", ()),
        ]:
            cmd = _patch_command(monkeypatch, symbol)
            argv = [command]
            if command == "desk-duration":
                argv.append("--bond")
                argv.append("OP-1")
            elif command == "desk-repo":
                argv.extend(["--bond", "OP-2"])
            assert main_mod.main(argv) == 0
            if args:
                cmd.assert_awaited_once_with(*args)
            else:
                cmd.assert_awaited_once()

    def test_alerts_check(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        cmd = _patch_command(monkeypatch, "cmd_alerts_check")
        assert main_mod.main(["alerts-check"]) == 0
        cmd.assert_awaited_once()

    def test_fx_commands(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        fetch = _patch_command(monkeypatch, "_cmd_fx_fetch")
        assert main_mod.main(["fx-fetch"]) == 0
        fetch.assert_awaited_once()
        metals = _patch_command(monkeypatch, "_cmd_fx_metals")
        assert main_mod.main(["fx-metals"]) == 0
        metals.assert_awaited_once()

    def test_seo_sitemap_skipped(self, monkeypatch, capsys):
        _patch_main_deps(monkeypatch)
        monkeypatch.setattr("api.seo.regenerate_sitemap", AsyncMock(return_value=None))
        assert main_mod.main(["seo-sitemap"]) == 0
        assert "skipped" in capsys.readouterr().out

    def test_seo_sitemap_written(self, monkeypatch, capsys):
        _patch_main_deps(monkeypatch)
        monkeypatch.setattr("api.seo.regenerate_sitemap", AsyncMock(return_value="<urlset/>"))
        assert main_mod.main(["seo-sitemap"]) == 0
        assert "written" in capsys.readouterr().out

    def test_no_args_exits_with_error(self, monkeypatch, capsys):
        _patch_main_deps(monkeypatch)
        with pytest.raises(SystemExit) as exc:
            main_mod.main([])
        assert exc.value.code == 2

    def test_unknown_command_exits_with_error(self, monkeypatch):
        _patch_main_deps(monkeypatch)
        with pytest.raises(SystemExit) as exc:
            main_mod.main(["nope"])
        assert exc.value.code == 2

    def test_main_guard_subprocess(self):
        import os
        import subprocess
        import sys

        env = {
            **os.environ,
            "DATABASE_URL": "postgresql+asyncpg://user:pass@127.0.0.1:1/none",
        }
        proc = subprocess.run(
            [sys.executable, "-m", "scraper"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        assert proc.returncode == 2  # argparse: subcommand required


class TestCompatShims:
    def test_parser_shims_re_export(self):
        import scraper.parsers.detail as detail_shim
        import scraper.parsers.history as history_shim
        import scraper.parsers.listing as listing_shim

        assert callable(detail_shim.parse_detail_html)
        assert callable(history_shim.parse_history_html)
        assert callable(listing_shim.parse_listing_html)

    def test_api_shims_re_export(self):
        import scraper.api.detail as api_detail
        import scraper.api.history as api_history
        import scraper.api.listing as api_listing

        assert callable(api_detail.parse_detail_payload)
        assert callable(api_history.parse_history_payload)
        assert callable(api_listing.parse_listing_payload)
