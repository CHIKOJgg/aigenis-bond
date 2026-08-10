"""Tests for monitoring/metrics.py, telegram_bot/metrics.py, _bot_instance.py."""

from __future__ import annotations

import monitoring.metrics as m
import telegram_bot._bot_instance as bi
import telegram_bot.metrics as tmetrics


class TestInProcessMetrics:
    def test_inc_default(self):
        before = m._metrics.get("api_requests", 0)
        m.inc("api_requests")
        assert m._metrics["api_requests"] == before + 1

    def test_inc_unknown_name_defaults_zero(self):
        m.inc("unknown_metric_xyz")
        assert m._metrics["unknown_metric_xyz"] == 1

    def test_inc_non_numeric_resets(self):
        m.set_metric("weird", "text")
        m.inc("weird", 2)
        assert m._metrics["weird"] == 2

    def test_set_metric(self):
        m.set_metric("bonds_total", 42)
        assert m._metrics["bonds_total"] == 42

    def test_get_metrics_includes_uptime(self):
        report = m.get_metrics()
        assert "uptime_seconds" in report
        assert report["uptime_seconds"] >= 0
        assert report["started_at"] == m._metrics["started_at"]

    def test_get_metrics_bad_started_at(self):
        m.set_metric("started_at", "nope")
        report = m.get_metrics()
        assert "uptime_seconds" in report
        m.set_metric("started_at", m._metrics["started_at"])

    def test_timed_sets_duration(self):
        @m.timed("scrape")
        def work():
            return 5

        assert work() == 5
        assert "last_scrape_duration_ms" in m._metrics
        assert m._metrics["last_scrape_duration_ms"] >= 0

    def test_timed_sets_duration_on_error(self):
        @m.timed("scrape")
        def boom():
            raise ValueError("x")

        import pytest

        with pytest.raises(ValueError):
            boom()
        assert "last_scrape_duration_ms" in m._metrics

    def test_timed_async(self):
        import asyncio

        async def coro():
            return "done"

        assert asyncio.run(m.timed_async("scrape", coro())) == "done"
        assert "last_scrape_duration_ms" in m._metrics

    def test_timed_async_error(self):
        import asyncio

        import pytest

        async def boom():
            raise RuntimeError("y")

        with pytest.raises(RuntimeError):
            asyncio.run(m.timed_async("scrape", boom()))
        assert "last_scrape_duration_ms" in m._metrics


class TestPrometheusMetrics:
    def test_counters_exist(self):
        tmetrics.bot_commands.labels(command="start").inc()
        tmetrics.bot_errors.labels(error_type="crash").inc()

    def test_latency_histogram(self):
        tmetrics.bot_latency.labels(command="help").observe(0.25)

    def test_db_query_histogram_custom_buckets(self):
        assert tmetrics.db_query_time._upper_bounds[:6] == [0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
        assert tmetrics.db_query_time._upper_bounds[-1] == float("inf")


class TestBotInstance:
    def test_roundtrip(self):
        bi.clear_bot()
        assert bi.get_bot() is None
        instance = object()
        bi.set_bot(instance)
        assert bi.get_bot() is instance
        bi.clear_bot()
        assert bi.get_bot() is None
