"""Tests for scraper/commands_v4 (desk: curve, rv, duration, carry, repo, stress)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from scraper.db import session_scope
from scraper.orm import BondORM


async def _add_bond(session, internal_id: str, currency: str = "USD") -> None:
    session.add(
        BondORM(
            internal_id=internal_id,
            name=f"Bond {internal_id}",
            currency=currency,
            market="bcse",
            status="active",
            nominal=Decimal("1000"),
            coupon_rate=Decimal("8"),
            coupon_frequency=2,
            maturity_date=date(2030, 1, 1),
            price=Decimal("100"),
            yield_to_maturity=Decimal("8"),
            issuer="MISIS",
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await session.flush()


def _pt(tenor: str = "1Y", years: float = 1.0, rate_pct: float = 8.0):
    return SimpleNamespace(tenor=tenor, years=years, rate_pct=rate_pct)


def _curve(points):
    return SimpleNamespace(points=points, slope=lambda: 1.2345)


def _params():
    return SimpleNamespace(model_dump=lambda: {"a": 1})


@pytest.mark.asyncio
async def test_fetch_bonds_with_rows():
    from scraper.commands_v4 import _fetch_bonds

    async with session_scope() as session:
        from sqlalchemy import delete

        await session.execute(delete(BondORM))
        await _add_bond(session, "CV4-1", "USD")
        await _add_bond(session, "CV4-2", "USD")
    bonds = await _fetch_bonds()
    assert len(bonds) == 2
    assert bonds[0].currency == "USD"


@pytest.mark.asyncio
async def test_cmd_desk_curve_variants(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scraper import commands_v4

    monkeypatch.setattr(commands_v4.yield_curve, "curve_from_bonds", lambda bs: _curve([]))
    assert await commands_v4.cmd_desk_curve() == 0
    assert "{}" in capsys.readouterr().out

    monkeypatch.setattr(commands_v4.yield_curve, "curve_from_bonds", lambda bs: _curve([_pt()]))
    monkeypatch.setattr(commands_v4.yield_curve, "fit_nelson_siegel", lambda pts: _params())
    save = AsyncMock()
    monkeypatch.setattr(commands_v4, "save_curve_points", save)
    assert await commands_v4.cmd_desk_curve() == 0
    assert save.await_count == 1
    assert '"slope": 1.2345' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cmd_desk_rv(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scraper import commands_v4

    def signals(_bonds):
        return [
            SimpleNamespace(
                side="buy", internal_id="B1", z_score=1.5, spread_pct=0.2, rationale="cheap"
            ),
            SimpleNamespace(
                side="sell", internal_id="B2", z_score=-1.2, spread_pct=-0.1, rationale="rich"
            ),
        ]

    monkeypatch.setattr(commands_v4.relative_value, "relative_value_signals", signals)
    save = AsyncMock()
    monkeypatch.setattr(commands_v4, "save_rv_signals", save)
    assert await commands_v4.cmd_desk_rv() == 0
    assert save.await_count == 1
    out = capsys.readouterr().out
    assert '"id": "B1"' in out and '"id": "B2"' in out


@pytest.mark.asyncio
async def test_cmd_desk_duration_variants(monkeypatch, capsys):
    from scraper import commands_v4

    report = SimpleNamespace(model_dump=lambda mode="python": {"dur": 3.5})

    async with session_scope() as session:
        await _add_bond(session, "CV4-D", "USD")

    monkeypatch.setattr(commands_v4.duration, "duration_report", lambda b: report)
    assert await commands_v4.cmd_desk_duration(internal_id="CV4-D") == 0
    assert '"dur": 3.5' in capsys.readouterr().out

    assert await commands_v4.cmd_desk_duration(internal_id="NOPE") == 1
    assert "not found" in capsys.readouterr().out

    monkeypatch.setattr(
        commands_v4.duration, "portfolio_duration", lambda bonds, weights=None: report
    )
    assert await commands_v4.cmd_desk_duration() == 0


@pytest.mark.asyncio
async def test_cmd_desk_carry(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scraper import commands_v4

    def rank_carry(_bonds, funding_rate_pct):
        return [
            SimpleNamespace(
                internal_id="B1",
                coupon_pct=8.0,
                funding_rate_pct=5.0,
                rolldown_bps=10,
                expected_pnl_pct=1.5,
            )
        ]

    monkeypatch.setattr(commands_v4.carry, "rank_carry", rank_carry)
    save = AsyncMock()
    monkeypatch.setattr(commands_v4, "save_carry_trades", save)
    assert await commands_v4.cmd_desk_carry() == 0
    assert save.await_count == 1
    assert '"id": "B1"' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cmd_desk_repo_variants(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scraper import commands_v4

    async with session_scope() as session:
        await _add_bond(session, "CV4-R", "USD")

    assert await commands_v4.cmd_desk_repo(internal_id="NOPE") == 1
    assert "not found" in capsys.readouterr().out

    deal = SimpleNamespace(model_dump=lambda mode="python": {"bond": "CV4-R"})
    monkeypatch.setattr(commands_v4.repo, "haircut_by_issuer", lambda issuer: 5.0)
    monkeypatch.setattr(commands_v4.repo, "repo_deal", lambda *a, **kw: deal)
    save = AsyncMock()
    monkeypatch.setattr(commands_v4, "save_repo_deal", save)
    assert await commands_v4.cmd_desk_repo(internal_id="CV4-R") == 0
    assert save.await_count == 1
    assert '"bond": "CV4-R"' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cmd_desk_stress(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scraper import commands_v4

    monkeypatch.setattr(
        commands_v4.stress,
        "PRESET_SCENARIOS",
        {"shock1": {"shock": 1}},
    )

    def run_stress(_scn, _items):
        return SimpleNamespace(pnl_pct=-5.0, pnl=Decimal("-50"), stressed_value=Decimal("950"))

    monkeypatch.setattr(commands_v4.stress, "run_stress", run_stress)
    save = AsyncMock()
    monkeypatch.setattr(commands_v4, "save_stress_run", save)
    assert await commands_v4.cmd_desk_stress() == 0
    assert save.await_count == 1
    assert '"shock1"' in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cmd_desk_status(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scraper import commands_v4

    rv_row = SimpleNamespace(internal_id="B1", z_score=Decimal("1.5"), side="buy")
    stress_row = SimpleNamespace(
        scenario_name="shock1",
        pnl_pct=Decimal("-5"),
        asof_date=date(2026, 1, 1),
    )
    monkeypatch.setattr(commands_v4, "latest_rv_signals", AsyncMock(return_value=[rv_row]))
    monkeypatch.setattr(commands_v4, "latest_stress_runs", AsyncMock(return_value=[stress_row]))
    assert await commands_v4.cmd_desk_status() == 0
    out = capsys.readouterr().out
    assert '"id": "B1"' in out and '"name": "shock1"' in out


@pytest.mark.asyncio
async def test_cmd_alerts_check(monkeypatch, capsys):
    async def checks():
        return 3

    monkeypatch.setattr("notifications.alerts_service.run_alert_checks", checks)
    assert (
        await __import__("scraper.commands_v4", fromlist=["cmd_alerts_check"]).cmd_alerts_check()
        == 0
    )
    assert '"fired_alerts": 3' in capsys.readouterr().out
