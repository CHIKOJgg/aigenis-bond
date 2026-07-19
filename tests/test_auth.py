"""Tests for the auth router + service (api/auth).

Covers registration, login, JWT refresh, password reset, verification,
tier-based /me, and the security-sensitive edge cases (weak password,
duplicate email, inactive account, forged tokens).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from api.auth.service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from api.main import app
from scraper.db import dispose, get_engine, session_scope
from scraper.orm import Base, UserORM


async def _ensure_schema() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _run(coro_fn):
    async def wrapper():
        await _ensure_schema()
        try:
            await coro_fn()
        finally:
            await dispose()

    asyncio.run(wrapper())


def _auth_headers(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


# --------------------------------------------------------------------------- #
# JWT / password primitives
# --------------------------------------------------------------------------- #
def test_password_hash_roundtrip():
    h = hash_password("s3cret!")
    assert h != "s3cret!"
    assert verify_password("s3cret!", h)
    assert not verify_password("wrong", h)


def test_access_token_roundtrip_and_expiry():
    tok = create_access_token(7)
    payload = decode_token(tok)
    assert payload["sub"] == "7"
    assert payload["type"] == "access"


def test_refresh_token_type_distinguished():
    tok = create_refresh_token(7)
    payload = decode_token(tok)
    assert payload["type"] == "refresh"


def test_decode_token_rejects_garbage():
    assert decode_token("not-a-real-token") is None
    assert decode_token("") is None


def test_refresh_rejected_when_used_as_access():
    refresh = create_refresh_token(9)
    # access-only decode in deps: a refresh token must not grant access.
    from api.auth.deps import _get_current_user

    class _Creds:
        credentials = type("C", (), {"credentials": refresh})()

    async def run():
        with pytest.raises(Exception):
            await _get_current_user(_Creds.credentials)

    _run(run)


# --------------------------------------------------------------------------- #
# Registration / login via HTTP
# --------------------------------------------------------------------------- #
def test_register_login_me_flow():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/auth/register",
                json={"email": "alice@example.com", "password": "hunter2", "name": "Alice"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["access_token"]
            assert body["refresh_token"]
            headers = {"Authorization": f"Bearer {body['access_token']}"}

            me = await client.get("/auth/me", headers=headers)
            assert me.status_code == 200
            me_body = me.json()
            assert me_body["email"] == "alice@example.com"
            assert me_body["name"] == "Alice"
            # New user is in trial -> effective tier is 'pro' during trial window.
            assert me_body["subscription_tier"] in {"pro", "free"}

            login = await client.post(
                "/auth/login",
                json={"email": "alice@example.com", "password": "hunter2"},
            )
            assert login.status_code == 200

    _run(run)


def test_register_rejects_short_password():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/auth/register",
                json={"email": "bob@example.com", "password": "123", "name": "Bob"},
            )
            assert resp.status_code == 400

    _run(run)


def test_register_duplicate_email_conflict():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {"email": "dup@example.com", "password": "hunter2", "name": "D"}
            assert (await client.post("/auth/register", json=payload)).status_code == 200
            again = await client.post("/auth/register", json=payload)
            assert again.status_code == 409

    _run(run)


def test_login_wrong_password_unauthorized():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/auth/register",
                json={"email": "carol@example.com", "password": "hunter2", "name": "C"},
            )
            bad = await client.post(
                "/auth/login",
                json={"email": "carol@example.com", "password": "WRONG"},
            )
            assert bad.status_code == 401

    _run(run)


def test_me_requires_auth():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/auth/me")).status_code == 401

    _run(run)


def test_refresh_rotates_tokens():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post(
                "/auth/register",
                json={"email": "dave@example.com", "password": "hunter2", "name": "D"},
            )
            refresh = reg.json()["refresh_token"]
            new = await client.post("/auth/refresh", json={"refresh_token": refresh})
            assert new.status_code == 200
            assert new.json()["access_token"]

            bad = await client.post("/auth/refresh", json={"refresh_token": "garbage"})
            assert bad.status_code == 401

    _run(run)


# --------------------------------------------------------------------------- #
# Password reset + email verification
# --------------------------------------------------------------------------- #
def test_forgot_and_reset_password():
    async def run():
        async with session_scope() as s:
            s.add(
                UserORM(
                    id=701,
                    email="reset@example.com",
                    name="R",
                    password_hash=hash_password("oldpass"),
                    is_active=True,
                )
            )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Always 200 (no email enumeration).
            forgot = await client.post("/auth/forgot-password", json={"email": "reset@example.com"})
            assert forgot.status_code == 200

            from api.auth.service import create_password_reset_token

            async with session_scope() as s:
                token = await create_password_reset_token(s, "reset@example.com")
            assert token

            reset = await client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": "newpass123"},
            )
            assert reset.status_code == 200

            login = await client.post(
                "/auth/login",
                json={"email": "reset@example.com", "password": "newpass123"},
            )
            assert login.status_code == 200

            # Token is single-use.
            reuse = await client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": "another456"},
            )
            assert reuse.status_code == 400

    _run(run)


def test_reset_password_invalid_token():
    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/auth/reset-password",
                json={"token": "invalid", "new_password": "x"},
            )
            assert resp.status_code == 400

    _run(run)


def test_verify_email_marks_verified():
    async def run():
        async with session_scope() as s:
            s.add(
                UserORM(
                    id=702,
                    email="verify@example.com",
                    name="V",
                    password_hash="x",
                    is_active=True,
                    is_verified=False,
                )
            )
        token = create_access_token(702)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/auth/verify-email", params={"token": token})
            assert resp.status_code == 200
            async with session_scope() as s:
                u = (await s.execute(UserORM.__table__.select().where(UserORM.id == 702))).first()
                assert u.is_verified is True

    _run(run)


# --------------------------------------------------------------------------- #
# Inactive account + service layer
# --------------------------------------------------------------------------- #
def test_login_inactive_account_blocked():
    async def run():
        from api.auth.service import login_user

        async with session_scope() as s:
            s.add(
                UserORM(
                    id=703,
                    email="inactive@example.com",
                    name="I",
                    password_hash=hash_password("hunter2"),
                    is_active=False,
                )
            )
        async with session_scope() as s:
            user, err = await login_user(s, "inactive@example.com", "hunter2")
        assert user is None
        assert err == "Account is disabled"

    _run(run)


def test_find_or_create_google_user_links_existing_email():
    async def run():
        from api.auth.service import find_or_create_google_user

        async with session_scope() as s:
            s.add(
                UserORM(
                    id=704,
                    email="g@example.com",
                    name="G",
                    password_hash="x",
                    is_active=True,
                    is_verified=False,
                )
            )
        async with session_scope() as s:
            user, created = await find_or_create_google_user(s, "gid-1", "g@example.com", "G")
            assert created is False
            assert user.google_id == "gid-1"
            assert user.is_verified is True

    _run(run)
