"""Unit tests for monitoring engine (monitoring/engine)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from monitoring.engine import (
    SOURCE_DEGRADED,
    SOURCE_DOWN,
    SOURCE_OK,
    assess_data_quality,
    classify_source_health,
)


class _Bond:
    def __init__(self, status="active", yield_to_maturity=10.0, fetched_at=None):
        self.status = status
        self.yield_to_maturity = yield_to_maturity
        self.fetched_at = fetched_at


def test_assess_data_quality_clean():
    now = datetime.now(UTC)
    bonds = [
        _Bond("active", 10.0, now - timedelta(hours=1)),
        _Bond("active", 8.0, now - timedelta(hours=1)),
    ]
    report = assess_data_quality(bonds, now=now)
    assert report.total == 2
    assert report.active == 2
    assert report.empty_ytm == 0
    assert report.issues == []
    assert classify_source_health(report) == SOURCE_OK


def test_assess_data_quality_empty_ytm_flagged():
    now = datetime.now(UTC)
    # 50% of active bonds lack YTM -> above threshold.
    bonds = [
        _Bond("active", None, now - timedelta(hours=1)),
        _Bond("active", 10.0, now - timedelta(hours=1)),
    ]
    report = assess_data_quality(bonds, now=now)
    assert report.empty_ytm == 1
    assert report.empty_ytm_pct == 50.0
    assert any("YTM" in i for i in report.issues)
    assert classify_source_health(report) == SOURCE_DEGRADED


def test_assess_data_quality_stale_flagged():
    now = datetime.now(UTC)
    old = now - timedelta(hours=100)
    bonds = [_Bond("active", 10.0, old), _Bond("active", 9.0, old)]
    report = assess_data_quality(bonds, now=now)
    assert report.stale_hours is not None and report.stale_hours >= 100
    assert any("устарели" in i for i in report.issues)
    assert classify_source_health(report) == SOURCE_DEGRADED


def test_assess_data_quality_empty_db_is_down():
    report = assess_data_quality([], now=datetime.now(UTC))
    assert report.total == 0
    assert classify_source_health(report) == SOURCE_DOWN


def test_classify_source_health_no_active_is_down():
    now = datetime.now(UTC)
    bonds = [_Bond("matured", 10.0, now - timedelta(hours=1))]
    report = assess_data_quality(bonds, now=now)
    assert report.active == 0
    assert classify_source_health(report) == SOURCE_DOWN
