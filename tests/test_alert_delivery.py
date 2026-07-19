"""Tests for alert delivery: Telegram + partner webhook fan-out.

Covers both alert pipelines that were previously silent:
* system monitoring alerts (monitoring.engine) -> partner alert.triggered webhook
* user-rule events (notifications.alerts_service) -> Telegram + partner webhook
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scraper.db import dispose, get_engine, get_session_factory
from scraper.orm import (
    AlertRuleORM,
    Base,
    BondHistoryORM,
    BondORM,
    UserORM,
)


async def _setup_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
async def db():
    await _setup_db()
    factory = get_session_factory()
    async with factory() as session:
        yield session
    await dispose()


async def test_emit_partner_alert_routes_to_webhook(monkeypatch):
    captured = {}

    async def fake_emit(event_type, payload, wait=False):
        captured["event"] = event_type
        captured["payload"] = payload
        return 3

    monkeypatch.setattr("api.partner.webhooks.emit_webhook_event", fake_emit)

    from notifications.delivery import emit_partner_alert

    n = await emit_partner_alert(
        kind="yield_drop",
        title="X: доходность упала",
        message="YTM X изменился 12.0 -> 8.0",
        internal_id="X",
        alert_id=7,
    )

    assert n == 3
    assert captured["event"] == "alert.triggered"
    assert captured["payload"] == {
        "kind": "yield_drop",
        "title": "X: доходность упала",
        "message": "YTM X изменился 12.0 -> 8.0",
        "internal_id": "X",
        "alert_id": 7,
    }


async def test_monitoring_emits_webhook_on_yield_drop(db: AsyncSession, monkeypatch):
    called = {}

    async def fake_emit(event_type, payload, wait=False):
        called.setdefault("events", []).append((event_type, payload))
        return 1

    monkeypatch.setattr("api.partner.webhooks.emit_webhook_event", fake_emit)

    now = datetime.now(UTC)
    db.add(
        BondORM(
            internal_id="X",
            name="Bond X",
            currency="USD",
            status="active",
            yield_to_maturity=Decimal("8.0"),
            price=Decimal("100"),
            coupon_rate=Decimal("5.0"),
            maturity_date=date(2030, 1, 1),
            fetched_at=now,
        )
    )
    db.add(
        BondHistoryORM(
            internal_id="X",
            date=date.today(),
            price=Decimal("100"),
            yield_=Decimal("12.0"),
            coupon=Decimal("5.0"),
        )
    )
    await db.commit()

    from monitoring.engine import detect_bond_changes

    result = await detect_bond_changes(db)
    assert result.by_kind.get("yield_drop") == 1
    assert called["events"]
    (event_type, payload) = called["events"][0]
    assert event_type == "alert.triggered"
    assert payload["kind"] == "yield_drop"
    assert payload["internal_id"] == "X"


async def test_user_rule_alert_emits_webhook(db: AsyncSession, monkeypatch):
    called = {}

    async def fake_emit(event_type, payload, wait=False):
        called.setdefault("events", []).append((event_type, payload))
        return 1

    monkeypatch.setattr("api.partner.webhooks.emit_webhook_event", fake_emit)

    now = datetime.now(UTC)
    db.add(
        BondORM(
            internal_id="R",
            name="Rule Bond",
            currency="USD",
            status="active",
            yield_to_maturity=Decimal("13.0"),
            price=Decimal("99"),
            maturity_date=date(2030, 1, 1),
            fetched_at=now,
        )
    )
    db.add(UserORM(id=42, email="u@example.com", name="U", telegram_id=None))
    db.add(
        AlertRuleORM(
            user_id=42,
            internal_id="R",
            metric="ytm",
            direction="above",
            threshold=Decimal("12.0"),
        )
    )
    await db.commit()

    from notifications.alerts_service import run_alert_checks

    fired = await run_alert_checks()
    assert fired == 1
    assert called["events"]
    (event_type, payload) = called["events"][0]
    assert event_type == "alert.triggered"
    assert payload["kind"] == "user_rule:ytm:above"
    assert payload["internal_id"] == "R"

    events = (await db.execute(select(UserORM))).scalars().all()
    assert events  # sanity: user persisted
    rule_events = (
        await db.execute(select(AlertRuleORM).where(AlertRuleORM.internal_id == "R"))
    ).scalars().all()
    assert rule_events[0].triggered_at is not None
