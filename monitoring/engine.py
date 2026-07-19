"""Мониторинг: обнаружение изменений и формирование алертов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from notifications.fx_repository import latest_fx, latest_metal, previous_fx, previous_metal
from notifications.repository import add_alert
from scraper.orm import BondHistoryORM, BondORM, BondScoreORM

THRESHOLDS = {
    "yield_drop_pct": 0.5,
    "yield_rise_pct": 0.5,
    "coupon_change_pct": 0.1,
    "price_change_pct": 1.0,
    "fx_change_pct": 0.5,
    "metal_change_pct": 0.5,
    "high_score": 90.0,
    # Data-quality guards: protect analytics from silent data rot.
    "empty_ytm_pct": 20.0,
    "stale_hours": 12.0,
}


@dataclass
class MonitoringResult:
    new_alerts: int
    by_kind: dict[str, int]


def _pct_change(old: float, new: float) -> float:
    if old == 0:
        return float("inf") if new != 0 else 0.0
    return (new - old) / abs(old) * 100


async def _latest_history(
    session: AsyncSession, internal_id: str
) -> BondHistoryORM | None:
    """Most recent historical snapshot for a bond (used for change detection)."""
    result = await session.execute(
        select(BondHistoryORM)
        .where(BondHistoryORM.internal_id == internal_id)
        .order_by(BondHistoryORM.date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _add_and_publish(session: AsyncSession, alert: dict) -> int | None:
    """Persist an alert (dedup-aware) and best-effort emit a partner webhook.

    Returns the new alert id, or ``None`` when the alert was suppressed as a
    duplicate (within the 24h dedup window). System alerts have no user, so
    delivery is via partner ``alert.triggered`` webhooks only.
    """
    alert_id = await add_alert(session, alert)
    if alert_id is not None:
        from notifications.delivery import emit_partner_alert

        await emit_partner_alert(
            kind=alert["kind"],
            title=alert["title"],
            message=alert["message"],
            internal_id=alert.get("internal_id"),
            alert_id=alert_id,
        )
    return alert_id


async def _emit_change_alert(
    session: AsyncSession,
    counts: dict[str, int],
    *,
    kind: str,
    title: str,
    message: str,
    internal_id: str,
    dedup_key: str,
) -> bool:
    """Persist a change alert, updating ``counts`` on success. Returns True if added."""
    alert_id = await _add_and_publish(
        session,
        {
            "kind": kind,
            "title": title,
            "message": message,
            "internal_id": internal_id,
            "dedup_key": dedup_key,
        },
    )
    if alert_id:
        counts[kind] = counts.get(kind, 0) + 1
        return True
    return False


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
            alert_id = await _add_and_publish(
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
            alert_id = await _add_and_publish(
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

        # Change detection vs the previous historical snapshot. This is the core
        # of ``detect_bond_changes`` — without it yield/coupon/price moves are
        # never surfaced (the THRESHOLDS below were previously dead).
        if b.status == "active":
            prev = await _latest_history(session, b.internal_id)
            if prev is not None:
                if b.yield_to_maturity is not None and prev.yield_ is not None:
                    dy = float(b.yield_to_maturity) - float(prev.yield_)
                    # Pick the alert spec (kind/title/dir) for the direction of
                    # the move; emit exactly one yield alert per bond per run.
                    if dy <= -THRESHOLDS["yield_drop_pct"]:
                        yspec = (
                            "yield_drop",
                            f"{b.name}: доходность упала",
                            f"YTM {b.internal_id} изменился с {prev.yield_} "
                            f"на {b.yield_to_maturity} ({dy:+.2f} п.п.)",
                        )
                    elif dy >= THRESHOLDS["yield_rise_pct"]:
                        yspec = (
                            "yield_rise",
                            f"{b.name}: доходность выросла",
                            f"YTM {b.internal_id} изменился с {prev.yield_} "
                            f"на {b.yield_to_maturity} ({dy:+.2f} п.п.)",
                        )
                    else:
                        yspec = None
                    if yspec is not None and await _emit_change_alert(
                        session,
                        counts,
                        kind=yspec[0],
                        title=yspec[1],
                        message=yspec[2],
                        internal_id=b.internal_id,
                        dedup_key=f"{yspec[0]}:{b.internal_id}:{date.today().isoformat()}",
                    ):
                        total_new += 1
                if b.coupon_rate is not None and prev.coupon is not None:
                    dc = float(b.coupon_rate) - float(prev.coupon)
                    if abs(dc) >= THRESHOLDS["coupon_change_pct"] and await _emit_change_alert(
                        session,
                        counts,
                        kind="coupon_change",
                        title=f"{b.name}: изменение купона",
                        message=(
                            f"Купон {b.internal_id} изменился с {prev.coupon} "
                            f"на {b.coupon_rate} ({dc:+.2f} п.п.)"
                        ),
                        internal_id=b.internal_id,
                        dedup_key=f"coupon:{b.internal_id}:{date.today().isoformat()}",
                    ):
                        total_new += 1
                if b.price is not None and prev.price is not None:
                    dp = _pct_change(float(prev.price), float(b.price))
                    if abs(dp) >= THRESHOLDS["price_change_pct"] and await _emit_change_alert(
                        session,
                        counts,
                        kind="price_change",
                        title=f"{b.name}: изменение цены",
                        message=(
                            f"Цена {b.internal_id} изменилась с {prev.price} "
                            f"на {b.price} ({dp:+.2f}%)"
                        ),
                        internal_id=b.internal_id,
                        dedup_key=f"price:{b.internal_id}:{date.today().isoformat()}",
                    ):
                        total_new += 1

    score_res = await session.execute(
        select(BondScoreORM).where(BondScoreORM.score >= THRESHOLDS["high_score"])
    )
    for s in score_res.scalars():
        alert_id = await _add_and_publish(
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
            alert_id = await _add_and_publish(
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
            alert_id = await _add_and_publish(
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


@dataclass
class DataQualityReport:
    total: int
    active: int
    empty_ytm: int
    empty_ytm_pct: float
    latest_fetch: datetime | None
    stale_hours: float | None
    issues: list[str]


def assess_data_quality(bonds, now: datetime | None = None) -> DataQualityReport:
    """Pure data-quality assessment over a list of bond ORM rows.

    Flags two silent-failure modes that would corrupt analytics:
    * too many active bonds missing YTM;
    * the freshest data being older than ``stale_hours``.
    """
    now = now or datetime.now(UTC)
    active = [b for b in bonds if getattr(b, "status", None) == "active"]
    total_active = len(active)
    empty_ytm = sum(1 for b in active if getattr(b, "yield_to_maturity", None) in (None,))
    empty_pct = (empty_ytm / total_active * 100) if total_active else 0.0

    fetch_times = [b.fetched_at for b in bonds if getattr(b, "fetched_at", None) is not None]
    latest = max(fetch_times) if fetch_times else None
    stale_hours: float | None = None
    if latest is not None:
        latest_aware = latest if latest.tzinfo else latest.replace(tzinfo=UTC)
        stale_hours = (now - latest_aware).total_seconds() / 3600.0

    issues: list[str] = []
    if total_active and empty_pct >= THRESHOLDS["empty_ytm_pct"]:
        issues.append(
            f"{empty_pct:.0f}% активных облигаций без YTM ({empty_ytm}/{total_active})"
        )
    if stale_hours is not None and stale_hours >= THRESHOLDS["stale_hours"]:
        issues.append(f"данные устарели: последнее обновление {stale_hours:.0f}ч назад")
    if not fetch_times:
        issues.append("нет ни одной облигации с датой обновления")

    return DataQualityReport(
        total=len(bonds),
        active=total_active,
        empty_ytm=empty_ytm,
        empty_ytm_pct=empty_pct,
        latest_fetch=latest,
        stale_hours=stale_hours,
        issues=issues,
    )


# Source-health states used by the website/API to degrade gracefully when the
# upstream data source (Aigenis) is unavailable or returning stale data.
SOURCE_OK = "ok"
SOURCE_DEGRADED = "degraded"  # stale but present — show a warning banner
SOURCE_DOWN = "down"  # no usable data — block analytics, show fallback


def classify_source_health(report: DataQualityReport) -> str:
    """Map a data-quality report to a coarse source-health state."""
    if report.total == 0 or report.active == 0:
        return SOURCE_DOWN
    if not report.issues:
        return SOURCE_OK
    # Staleness / empty-YTM are degradation, not a hard outage.
    return SOURCE_DEGRADED


async def data_source_health(session: AsyncSession) -> dict[str, object]:
    """Snapshot of upstream data-source health for graceful degradation.

    Returns a small dict the API/website can embed in responses to decide
    whether to show live analytics, a 'data may be stale' banner, or a
    'service unavailable' fallback.
    """
    bonds = list((await session.execute(select(BondORM))).scalars().all())
    report = assess_data_quality(bonds)
    return {
        "status": classify_source_health(report),
        "total": report.total,
        "active": report.active,
        "empty_ytm_pct": round(report.empty_ytm_pct, 1),
        "latest_fetch": report.latest_fetch.isoformat() if report.latest_fetch else None,
        "stale_hours": round(report.stale_hours, 1) if report.stale_hours is not None else None,
        "issues": report.issues,
    }


async def detect_data_quality(session: AsyncSession) -> MonitoringResult:
    """Persist alerts for data-quality issues (empty YTM %, stale data)."""
    bonds = list((await session.execute(select(BondORM))).scalars().all())
    report = assess_data_quality(bonds)
    counts: dict[str, int] = {}
    total = 0
    for issue in report.issues:
        alert_id = await _add_and_publish(
            session,
            {
                "kind": "data_quality",
                "title": "⚠️ Качество данных",
                "message": issue,
                "dedup_key": f"data_quality:{hash(issue) % 10**8}:{date.today().isoformat()}",
            },
        )
        if alert_id:
            counts["data_quality"] = counts.get("data_quality", 0) + 1
            total += 1
    return MonitoringResult(new_alerts=total, by_kind=counts)


async def run_all(session: AsyncSession) -> dict[str, MonitoringResult]:
    results: dict[str, MonitoringResult] = {}
    for name, fn in (
        ("bonds", detect_bond_changes),
        ("fx", detect_fx_changes),
        ("metals", detect_metal_changes),
        ("data_quality", detect_data_quality),
    ):
        try:
            results[name] = await fn(session)
        except Exception:
            results[name] = MonitoringResult(new_alerts=0, by_kind={})
    return results
