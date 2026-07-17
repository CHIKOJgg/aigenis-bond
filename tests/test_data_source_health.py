from __future__ import annotations

from datetime import UTC, datetime, timedelta

from monitoring.engine import (
    SOURCE_DEGRADED,
    SOURCE_DOWN,
    SOURCE_OK,
    DataQualityReport,
    assess_data_quality,
    classify_source_health,
)


class _Bond:
    def __init__(self, status="active", ytm=5.0, fetched_at=None):
        self.status = status
        self.yield_to_maturity = ytm
        self.fetched_at = fetched_at


def test_classify_ok_when_fresh_and_complete():
    now = datetime.now(UTC)
    bonds = [_Bond(fetched_at=now - timedelta(hours=1)) for _ in range(5)]
    rep = assess_data_quality(bonds, now=now)
    assert rep.issues == []
    assert classify_source_health(rep) == SOURCE_OK


def test_classify_degraded_when_stale():
    now = datetime.now(UTC)
    bonds = [_Bond(fetched_at=now - timedelta(hours=48)) for _ in range(5)]
    rep = assess_data_quality(bonds, now=now)
    assert any("устарели" in i for i in rep.issues)
    assert classify_source_health(rep) == SOURCE_DEGRADED


def test_classify_down_when_no_data():
    rep = DataQualityReport(
        total=0, active=0, empty_ytm=0, empty_ytm_pct=0.0,
        latest_fetch=None, stale_hours=None, issues=["нет данных"],
    )
    assert classify_source_health(rep) == SOURCE_DOWN
