"""Tests for the admin panel security: brute-force protection and CSRF checks."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.fixture(autouse=True)
def _reset_admin_rate_limiter():
    """Each test gets a clean brute-force limiter.

    The limiter keys on the socket peer (proxy headers are only trusted with
    TRUSTED_PROXY=1), so ASGI tests share one key; without a reset the first
    test's 5 failed logins would 429 the later tests.
    """
    from api.admin.router import _LOGIN_ATTEMPTS, _LOGIN_LOCK

    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.clear()
    yield
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.clear()


@pytest.mark.asyncio
async def test_admin_login_is_rate_limited_after_failures():
    """Six failed logins from the same IP → 429 on the last one."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(5):
            resp = await client.post(
                "/admin/login",
                data={"email": "admin@example.com", "password": "wrong"},
                headers={"x-forwarded-for": "203.0.113.50"},
            )
            assert resp.status_code == 401
        resp = await client.post(
            "/admin/login",
            data={"email": "admin@example.com", "password": "wrong"},
            headers={"x-forwarded-for": "203.0.113.50"},
        )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_admin_login_rejects_cross_site_origin():
    """A forged Origin header from an attacker domain must be rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/admin/login",
            data={"email": "admin@example.com", "password": "whatever"},
            headers={"origin": "https://evil.example"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_state_changes_require_csrf_origin():
    """POST without Origin/Referer is a CSRF signal and must be rejected (not
    silently allowed). The auth check runs first, so the unauthenticated case
    redirects to login; with a valid admin cookie it must be a 403."""
    from api.auth.service import create_access_token
    from scraper.db import session_scope
    from scraper.orm import UserORM

    async with session_scope() as s:
        s.add(
            UserORM(
                id=9001,
                email="boss@example.com",
                name="Boss",
                password_hash="x",
                role="admin",
                is_active=True,
            )
        )
    token = create_access_token(9001)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Cross-site attacker (no cookie): must NOT reach the handler.
        resp = await client.post(
            "/admin/users/9001/toggle", headers={"origin": "https://evil.example"}
        )
        assert resp.status_code in (302, 403)

        # Authenticated but headers missing → CSRF rejection.
        resp = await client.post(
            "/admin/users/9001/toggle",
            headers={"cookie": f"admin_token={token}"},
        )
        assert resp.status_code == 403

        # Authenticated + valid same-origin header → allowed.
        resp = await client.post(
            "/admin/users/9001/toggle",
            headers={
                "cookie": f"admin_token={token}",
                "origin": "http://localhost",
            },
            follow_redirects=False,
        )
    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_admin_tier_change_requires_valid_origin():
    from api.auth.service import create_access_token
    from scraper.db import session_scope
    from scraper.orm import UserORM

    async with session_scope() as s:
        s.add(
            UserORM(
                id=9002,
                email="boss2@example.com",
                name="Boss2",
                password_hash="x",
                role="admin",
                is_active=True,
            )
        )
    token = create_access_token(9002)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/admin/users/9002/tier",
            data={"tier": "pro"},
            headers={"cookie": f"admin_token={token}", "origin": "https://attacker.net"},
        )
        assert resp.status_code == 403

        resp = await client.post(
            "/admin/users/9002/tier",
            data={"tier": "pro"},
            headers={"cookie": f"admin_token={token}", "origin": "https://aigenis.by"},
            follow_redirects=False,
        )
    assert resp.status_code == 302
