"""Tests for scraper/commands_v3 (ml-train, ml-predict, recs, rebalance-now)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from scraper.db import session_scope
from scraper.orm import BondHistoryORM, BondORM


async def _add_bond(session, internal_id: str) -> None:
    session.add(
        BondORM(
            internal_id=internal_id,
            name=f"Bond {internal_id}",
            currency="USD",
            market="bcse",
            status="active",
            nominal=Decimal("1000"),
            coupon_rate=Decimal("8"),
            coupon_frequency=2,
            maturity_date=date(2030, 1, 1),
            price=Decimal("100"),
            yield_to_maturity=Decimal("8"),
            fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await session.flush()


async def _add_history(session, internal_id: str) -> None:
    session.add(
        BondHistoryORM(
            internal_id=internal_id,
            date=date(2026, 1, 2),
            price=Decimal("101"),
            yield_=Decimal("7.9"),
            coupon=Decimal("8"),
            status="active",
        )
    )
    await session.flush()


def _model(version: str = "v1", metrics=None, artifact_path: str = "a"):
    return SimpleNamespace(
        version=version, metrics=metrics or {"mae": 1.0}, artifact_path=artifact_path
    )


def _samples(n: int = 30):
    return [{"internal_id": f"B{i}", "features": [1.0], "ytm": 8.0} for i in range(n)]


@pytest.mark.asyncio
async def test_fetch_bonds_dicts_with_rows():
    from scraper.commands_v3 import _fetch_bonds_dicts

    async with session_scope() as session:
        await _add_bond(session, "CV3-1")
        await _add_history(session, "CV3-1")
    bonds, history = await _fetch_bonds_dicts()
    assert bonds[0]["internal_id"] == "CV3-1"
    assert history["CV3-1"][0]["price"] == Decimal("101")
    assert history["CV3-1"][0]["yield"] == Decimal("7.9")


@pytest.mark.asyncio
async def test_cmd_ml_train_insufficient_samples(monkeypatch, capsys):
    from scraper import commands_v3

    monkeypatch.setattr(commands_v3, "build_training_samples", lambda *a: [])
    assert await commands_v3.cmd_ml_train() == 1
    assert "Недостаточно" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cmd_ml_train_classifier_skipped(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scraper import commands_v3

    monkeypatch.setattr(commands_v3, "build_training_samples", lambda *a: _samples())
    monkeypatch.setattr(commands_v3, "train_ytm_regressor", lambda s: (_model(), _model()))
    monkeypatch.setattr(
        commands_v3,
        "train_buy_classifier",
        lambda s: (_ for _ in ()).throw(ValueError("no diversity")),
    )
    upsert = AsyncMock()
    insert = AsyncMock()
    monkeypatch.setattr(commands_v3, "upsert_model_version", upsert)
    monkeypatch.setattr(commands_v3, "insert_training_run", insert)

    assert await commands_v3.cmd_ml_train() == 0
    assert upsert.await_count == 1
    assert insert.await_count == 1
    assert "buy_classifier" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cmd_ml_train_full_success(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scraper import commands_v3

    monkeypatch.setattr(commands_v3, "build_training_samples", lambda *a: _samples())
    monkeypatch.setattr(commands_v3, "train_ytm_regressor", lambda s: (_model(), _model()))
    monkeypatch.setattr(commands_v3, "train_buy_classifier", lambda s: (_model(), _model()))
    upsert = AsyncMock()
    insert = AsyncMock()
    monkeypatch.setattr(commands_v3, "upsert_model_version", upsert)
    monkeypatch.setattr(commands_v3, "insert_training_run", insert)

    assert await commands_v3.cmd_ml_train() == 0
    assert upsert.await_count == 2
    assert insert.await_count == 2


@pytest.mark.asyncio
async def test_cmd_ml_predict_variants(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scraper import commands_v3

    monkeypatch.setattr(commands_v3, "build_dataset", lambda *a: [])
    assert await commands_v3.cmd_ml_predict() == 1

    monkeypatch.setattr(commands_v3, "build_dataset", lambda *a: [{"f": 1}])
    monkeypatch.setattr(commands_v3, "latest_artifact", lambda kind: None)
    assert await commands_v3.cmd_ml_predict() == 1

    monkeypatch.setattr(commands_v3, "latest_artifact", lambda kind: f"{kind}.bin")
    monkeypatch.setattr("ml.engine.predict_batch", lambda f, **kw: [{"id": "B1"}])
    upsert = AsyncMock()
    monkeypatch.setattr(commands_v3, "upsert_predictions", upsert)
    assert await commands_v3.cmd_ml_predict() == 0
    assert upsert.await_count == 1
    assert "Predicted for 1 bonds" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cmd_recs(monkeypatch, capsys):
    from scraper import commands_v3

    rec = SimpleNamespace(
        rank=1,
        internal_id="B1",
        name="Bond B1",
        decision="buy",
        score=80,
        confidence=0.9,
    )
    monkeypatch.setattr(commands_v3, "recommend_bonds", lambda *a, **kw: [rec])
    assert await commands_v3.cmd_recs() == 0
    assert "BUY" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cmd_rebalance_now(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scoring.models import UserPreferences
    from scraper import commands_v3

    prefs = UserPreferences(user_id=0, initial_capital=Decimal("100000"))
    plan = SimpleNamespace(
        strategy="target",
        actions=[
            SimpleNamespace(
                side="buy",
                internal_id="B1",
                amount=Decimal("5000"),
                weight_before=Decimal("0.1"),
                weight_after=Decimal("0.2"),
            )
        ],
    )
    monkeypatch.setattr(commands_v3, "get_preferences_for_user", AsyncMock(return_value=prefs))
    monkeypatch.setattr(commands_v3, "list_positions", AsyncMock(return_value=[]))
    monkeypatch.setattr(commands_v3, "total_value", lambda positions: Decimal("0"))
    monkeypatch.setattr(
        commands_v3.repositories.bonds,
        "get_all_internal_ids",
        AsyncMock(return_value=["B1"]),
    )
    monkeypatch.setattr(commands_v3, "build_plan", lambda **kw: plan)

    assert await commands_v3.cmd_rebalance_now() == 0
    assert "План ребалансировки" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_cmd_rebalance_now_no_plan(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scoring.models import UserPreferences
    from scraper import commands_v3

    prefs = UserPreferences(user_id=0)
    monkeypatch.setattr(commands_v3, "get_preferences_for_user", AsyncMock(return_value=prefs))
    monkeypatch.setattr(commands_v3, "list_positions", AsyncMock(return_value=[]))
    monkeypatch.setattr(commands_v3, "total_value", lambda positions: Decimal("0"))
    monkeypatch.setattr(
        commands_v3.repositories.bonds, "get_all_internal_ids", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(commands_v3, "build_plan", lambda **kw: None)

    assert await commands_v3.cmd_rebalance_now() == 0
    assert "не требуется" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_get_preferences_for_user_real_path(monkeypatch):
    from unittest.mock import AsyncMock

    from scoring.models import UserPreferences
    from scraper.commands_v3 import get_preferences_for_user

    monkeypatch.setattr(
        "telegram_bot.preferences_repository.get_preferences",
        AsyncMock(return_value=UserPreferences(user_id=0)),
    )
    prefs = await get_preferences_for_user(None, 0)
    assert prefs.user_id == 0


@pytest.mark.asyncio
async def test_cmd_ml_status_with_and_without_models(monkeypatch, capsys):
    from unittest.mock import AsyncMock

    from scraper import commands_v3

    now = datetime(2026, 1, 1, tzinfo=UTC)
    mv = SimpleNamespace(version="v1", trained_at=now, metrics={"mae": 1.0}, artifact_path="a.bin")

    def side_effect(_session, _kind):
        call = latest.call_count
        return None if call == 1 else mv

    latest = AsyncMock(side_effect=side_effect)
    monkeypatch.setattr(commands_v3, "latest_model_version", latest)
    assert await commands_v3.cmd_ml_status() == 0
    out = capsys.readouterr().out
    assert '"ytm_regression": null' in out
    assert '"artifact_path": "a.bin"' in out
