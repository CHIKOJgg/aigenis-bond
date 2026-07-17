from __future__ import annotations

from scraper.observability import init_sentry


def test_init_sentry_no_dsn_returns_false(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry(None, environment="production") is False
    # development/test do not warn-but-still-false path; just ensure no crash
    assert init_sentry(None, environment="development") is False


def test_init_sentry_with_dsn_initializes(monkeypatch):
    import sentry_sdk

    calls: dict = {}

    def _fake_init(**kwargs):
        calls.update(kwargs)

    monkeypatch.setattr(sentry_sdk, "init", _fake_init)
    assert init_sentry("https://x@sentry.example/1", environment="production") is True
    assert calls.get("dsn") == "https://x@sentry.example/1"
    assert calls.get("environment") == "production"
    assert calls.get("send_default_pii") is False
