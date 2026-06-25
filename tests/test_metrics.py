from __future__ import annotations

from monitoring.metrics import get_metrics, inc, set_metric


def test_inc():
    before = get_metrics()["scrape_total"]
    inc("scrape_total")
    assert get_metrics()["scrape_total"] == before + 1


def test_set_metric():
    set_metric("test_value", 42)
    assert get_metrics()["test_value"] == 42


def test_get_metrics_includes_uptime():
    metrics = get_metrics()
    assert "uptime_seconds" in metrics
    assert metrics["uptime_seconds"] >= 0


def test_get_metrics_defaults():
    metrics = get_metrics()
    assert "scrape_total" in metrics
    assert "scrape_errors" in metrics
    assert "api_requests" in metrics
    assert "bot_commands" in metrics
