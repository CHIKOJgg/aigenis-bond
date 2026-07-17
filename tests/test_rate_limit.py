"""Tests for rate-limit identity resolution (api.main).

Ensures the limiter keys authenticated callers per user id (so shared-NAT users
don't exhaust each other) and only trusts X-Forwarded-For behind a configured
proxy — otherwise the header cannot be used to spoof a fresh identity.
"""
from __future__ import annotations

import api.main as main
from api.auth.service import create_access_token


class _FakeClient:
    def __init__(self, host: str):
        self.host = host


class _FakeRequest:
    def __init__(self, headers: dict[str, str], host: str = "10.0.0.9"):
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.client = _FakeClient(host)


def test_untrusted_proxy_ignores_forwarded_for(monkeypatch):
    monkeypatch.setattr(main, "_TRUSTED_PROXY", False)
    req = _FakeRequest({"X-Forwarded-For": "1.2.3.4"}, host="10.0.0.9")
    # Header must be ignored -> uses the real socket peer.
    assert main._client_ip(req) == "10.0.0.9"


def test_trusted_proxy_uses_last_forwarded_hop(monkeypatch):
    monkeypatch.setattr(main, "_TRUSTED_PROXY", True)
    req = _FakeRequest({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}, host="10.0.0.9")
    assert main._client_ip(req) == "5.6.7.8"


def test_authenticated_caller_keyed_by_user(monkeypatch):
    monkeypatch.setattr(main, "_TRUSTED_PROXY", False)
    token = create_access_token(4242)
    req = _FakeRequest({"Authorization": f"Bearer {token}"}, host="10.0.0.9")
    key, limit = main._rate_identity_and_limit(req)
    assert key == "user:4242"
    assert limit == main._RATE_LIMIT


def test_anonymous_caller_keyed_by_ip(monkeypatch):
    monkeypatch.setattr(main, "_TRUSTED_PROXY", False)
    req = _FakeRequest({}, host="203.0.113.5")
    key, _ = main._rate_identity_and_limit(req)
    assert key == "ip:203.0.113.5"


def test_two_users_same_ip_get_separate_budgets(monkeypatch):
    monkeypatch.setattr(main, "_TRUSTED_PROXY", False)
    req_a = _FakeRequest({"Authorization": f"Bearer {create_access_token(1)}"}, host="10.0.0.1")
    req_b = _FakeRequest({"Authorization": f"Bearer {create_access_token(2)}"}, host="10.0.0.1")
    key_a, _ = main._rate_identity_and_limit(req_a)
    key_b, _ = main._rate_identity_and_limit(req_b)
    assert key_a != key_b
