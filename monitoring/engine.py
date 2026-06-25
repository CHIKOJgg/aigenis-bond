"""Мониторинг: обнаружение изменений и формирование алертов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notifications.fx_repository import latest_fx, latest_metal, previous_fx, previous_metal
from notifications.repository import add_alert
from scraper.orm import BondORM, BondScoreORM

THRESHOLDS = {
    "yield_drop_pct": 0.5,
    "yield_rise_pct": 0.5,
    "coupon_change_pct": 0.1,
    "price_change_pct": 1.0,
    "fx_change_pct": 0.5,
    "metal_change_pct": 0.5,
    "high_score": 90.0,
}


@dataclass
class MonitoringResult:
    new_alerts: int
    by_kind: dict[str, int]


def _decimal(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / abs(old) * 100


async def detect_bond_changes(session: AsyncSession) -> MonitoringResult:
    """Сравнить текущие bond_history с предыдущим снимком; сгенерировать алерты."""
    result = await session.execute(select(BondORM))
    bonds = list(result.scalars().all())
    counts: dict[str, int] = {}
    total_new = 0

    seen_ids: set[str] = set()
    for b in bonds:
        seen_ids.add(b.internal_id)
        if b.status == "delisted" or b.status == "matured":
            alert_id = await add_alert(
                session,
                {
                    "kind": "matured" if b.status == "matured" else "delisted",
                    "title": f"{b.name}: статус {b.status}",
                    "message": f"Облигация {b.internal_id} ({b.name}) теперь {b.status}",
                    "internal_id": b.internal_id,
                    "dedup_key": f"status:{b.internal_id}:{b.status}",
                },
            )
            if alert_id:
                counts["matured" if b.status == "matured" else "delisted"] = (
                    counts.get("matured" if b.status == "matured" else "delisted", 0) + 1
                )
                total_new += 1

        if b.offer_date and b.offer_date >= date.today():
            alert_id = await add_alert(
                session,
                {
                    "kind": "offer",
                    "title": f"Оферта {b.name}",
                    "message": f"Оферта по {b.internal_id} {b.offer_date.isoformat()}",
                    "internal_id": b.internal_id,
                    "dedup_key": f"offer:{b.internal_id}:{b.offer_date.isoformat()}",
                },
            )
            if alert_id:
                counts["offer"] = counts.get("offer", 0) + 1
                total_new += 1

    score_res = await session.execute(
        select(BondScoreORM).where(BondScoreORM.score >= THRESHOLDS["high_score"])
    )
    for s in score_res.scalars():
        alert_id = await add_alert(
            session,
            {
                "kind": "high_score",
                "title": f"Высокий Score {float(s.score):.0f}",
                "message": f"{s.internal_id} набрал {float(s.score):.1f} баллов",
                "internal_id": s.internal_id,
                "dedup_key": f"high_score:{s.internal_id}:{s.computed_at.date().isoformat()}",
            },
        )
        if alert_id:
            counts["high_score"] = counts.get("high_score", 0) + 1
            total_new += 1

    return MonitoringResult(new_alerts=total_new, by_kind=counts)


async def detect_fx_changes(session: AsyncSession) -> MonitoringResult:
    counts: dict[str, int] = {}
    total = 0
    for pair in ("USD/BYN", "EUR/BYN", "EUR/USD"):
        cur = await latest_fx(session, pair)
        prev = await previous_fx(session, pair)
        if cur is None or prev is None:
            continue
        change = _pct_change(float(prev.rate), float(cur.rate))
        if abs(change) >= THRESHOLDS["fx_change_pct"]:
            kind = (
                "fx_usd_byn"
                if "USD" in pair and "BYN" in pair
                else f"fx_{pair.replace('/', '_').lower()}"
            )
            alert_id = await add_alert(
                session,
                {
                    "kind": kind,
                    "title": f"{pair}: {change:+.2f}%",
                    "message": f"Курс {pair} изменился с {prev.rate} на {cur.rate} ({change:+.2f}%)",
                    "payload": {"old": float(prev.rate), "new": float(cur.rate)},
                    "dedup_key": f"fx:{pair}:{cur.observed_at.date().isoformat()}",
                },
            )
            if alert_id:
                counts[kind] = counts.get(kind, 0) + 1
                total += 1
    return MonitoringResult(new_alerts=total, by_kind=counts)


async def detect_metal_changes(session: AsyncSession) -> MonitoringResult:
    counts: dict[str, int] = {}
    total = 0
    for metal in ("XAU", "XAG", "XPT"):
        cur = await latest_metal(session, metal)
        prev = await previous_metal(session, metal)
        if cur is None or prev is None:
            continue
        change = _pct_change(float(prev.price), float(cur.price))
        if abs(change) >= THRESHOLDS["metal_change_pct"]:
            kind = f"metal_{metal.lower()}"
            alert_id = await add_alert(
                session,
                {
                    "kind": kind,
                    "title": f"{metal}: {change:+.2f}%",
                    "message": f"Цена {metal} изменилась с {prev.price} на {cur.price} ({change:+.2f}%)",
                    "payload": {"old": float(prev.price), "new": float(cur.price)},
                    "dedup_key": f"metal:{metal}:{cur.observed_at.date().isoformat()}",
                },
            )
            if alert_id:
                counts[kind] = counts.get(kind, 0) + 1
                total += 1
    return MonitoringResult(new_alerts=total, by_kind=counts)


async def run_all(session: AsyncSession) -> dict[str, MonitoringResult]:
    return {
        "bonds": await detect_bond_changes(session),
        "fx": await detect_fx_changes(session),
        "metals": await detect_metal_changes(session),
    }
