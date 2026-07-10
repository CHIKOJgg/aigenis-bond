"""Tests for data-quality assessment (pure, no DB/network)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from monitoring.engine import assess_data_quality


class _Bond:
    def __init__(self, status="active", ytm=1.0, fetched=None):
        self.status = status
        self.yield_to_maturity = ytm
        self.fetched_at = fetched


def test_empty_ytm_flagged():
    now = datetime.now(UTC)
    bonds = [_Bond(ytm=None, fetched=now) for _ in range(3)] + [_Bond(ytm=1.0, fetched=now)]
    report = assess_data_quality(bonds, now=now)
    assert report.empty_ytm == 3
    assert report.empty_ytm_pct == 75.0
    assert any("YTM" in i for i in report.issues)


def test_stale_data_flagged():
    now = datetime.now(UTC)
    old = now - timedelta(hours=20)
    report = assess_data_quality([_Bond(ytm=1.0, fetched=old)], now=now)
    assert report.stale_hours is not None and report.stale_hours >= 12
    assert any("устарел" in i for i in report.issues)


def test_healthy_dataset_has_no_issues():
    now = datetime.now(UTC)
    bonds = [_Bond(ytm=1.0, fetched=now) for _ in range(10)]
    report = assess_data_quality(bonds, now=now)
    assert report.issues == []


def test_naive_fetched_at_is_normalised():
    now = datetime.now(UTC)
    naive_old = (now - timedelta(hours=15)).replace(tzinfo=None)
    report = assess_data_quality([_Bond(ytm=1.0, fetched=naive_old)], now=now)
    assert report.stale_hours is not None and report.stale_hours >= 12
