"""Tests for scraper/scheduler_v3 and scraper/scheduler_v4 job hooks."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_scheduled_ml_train_full_success(monkeypatch):
    from scraper import scheduler_v3

    monkeypatch.setattr(scheduler_v3, "cmd_ml_train", _mk_cmd(0))
    monkeypatch.setattr(scheduler_v3, "cmd_ml_predict", _mk_cmd(0))
    monkeypatch.setattr("ml.registry.prune_artifacts", lambda: ["a", "b"])

    assert await scheduler_v3.scheduled_ml_train() == 0


@pytest.mark.asyncio
async def test_scheduled_ml_train_predict_skipped_on_nonzero_rc(monkeypatch):
    from scraper import scheduler_v3

    monkeypatch.setattr(scheduler_v3, "cmd_ml_train", _mk_cmd(3))

    def predict_should_not_run():
        pytest.fail("predict must not run")

    monkeypatch.setattr(scheduler_v3, "cmd_ml_predict", predict_should_not_run)

    assert await scheduler_v3.scheduled_ml_train() == 0


@pytest.mark.asyncio
async def test_scheduled_ml_train_prune_failure_ignored(monkeypatch):
    from scraper import scheduler_v3

    monkeypatch.setattr(scheduler_v3, "cmd_ml_train", _mk_cmd(0))
    monkeypatch.setattr(scheduler_v3, "cmd_ml_predict", _mk_cmd(0))

    def prune_boom():
        raise RuntimeError("prune down")

    monkeypatch.setattr("ml.registry.prune_artifacts", prune_boom)

    assert await scheduler_v3.scheduled_ml_train() == 0


@pytest.mark.asyncio
async def test_scheduled_ml_train_failure_returns_zero(monkeypatch):
    from scraper import scheduler_v3

    async def train_boom():
        raise RuntimeError("ml train down")

    monkeypatch.setattr(scheduler_v3, "cmd_ml_train", train_boom)

    assert await scheduler_v3.scheduled_ml_train() == 0


@pytest.mark.asyncio
async def test_scheduled_auto_rebalance_ok_and_failure(monkeypatch):
    from scraper import scheduler_v3

    monkeypatch.setattr(scheduler_v3, "cmd_rebalance_now", _mk_cmd(0))
    assert await scheduler_v3.scheduled_auto_rebalance() == 0

    async def rebalance_boom():
        raise RuntimeError("rebalance down")

    monkeypatch.setattr(scheduler_v3, "cmd_rebalance_now", rebalance_boom)
    assert await scheduler_v3.scheduled_auto_rebalance() == 0


@pytest.mark.asyncio
async def test_scheduled_v4_commands_ok_and_failure(monkeypatch):
    from scraper import scheduler_v4

    for func_name, cmd_name in (
        ("scheduled_curve", "cmd_desk_curve"),
        ("scheduled_rv", "cmd_desk_rv"),
        ("scheduled_stress", "cmd_desk_stress"),
    ):
        monkeypatch.setattr(scheduler_v4, cmd_name, _mk_cmd(0))
        assert await getattr(scheduler_v4, func_name)() == 0

        async def boom(cmd_name=cmd_name):
            raise RuntimeError(f"{cmd_name} down")

        monkeypatch.setattr(scheduler_v4, cmd_name, boom)
        assert await getattr(scheduler_v4, func_name)() == 0


@pytest.mark.asyncio
async def test_scheduled_alerts_ok_and_failure(monkeypatch):
    from scraper import scheduler_v4

    async def checks():
        return 7

    monkeypatch.setattr("notifications.alerts_service.run_alert_checks", checks)
    assert await scheduler_v4.scheduled_alerts() == 0

    async def checks_boom():
        raise RuntimeError("alerts down")

    monkeypatch.setattr("notifications.alerts_service.run_alert_checks", checks_boom)
    assert await scheduler_v4.scheduled_alerts() == 0


def _mk_cmd(rc: int):
    async def cmd():
        return rc

    return cmd
