"""Phase 5 tests: SSO security (5.8), entitlement scopes (5.9), provider
contract (5.5), instrument_map DB repository (5.14), alembic chain, and the
integration API namespace (5.11-5.13).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa as py_rsa

os.environ.setdefault("AIGENIS_ENVIRONMENT", "staging")
os.environ.setdefault("AIGENIS_SSO_ENABLED", "0")

ISSUER = "https://sso.aigenis.test/"
AUDIENCE = "aigenis-analytics"


# ──────────────────────────────────────────────
# JWT / JWKS helpers
# ──────────────────────────────────────────────


def _jwks_pair():
    """Return (private_key, jwks_dict) for python-jose RS256 round-trip."""
    from jose.jwk import RSAKey

    private = py_rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAKey(private.public_key(), algorithm="RS256")
    jwks = {"keys": [jwk.to_dict()]}
    return private, jwks


def _token(private, claims: dict) -> str:
    from jose import jwt as jose

    return jose.encode(claims, private, algorithm="RS256")


def _claims(sub: str = "u-42", scopes: list[str] | None = None) -> dict:
    return {
        "sub": sub,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "exp": int(time.time()) + 3600,
        "tenant": "aigenis",
        "tier": "premium",
        "scopes": scopes or [],
    }


def _request(*, token: str | None = None) -> object:
    from starlette.requests import Request

    headers = [(b"host", b"test"), (b"user-agent", b"pytest")]
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    scope = {
        "type": "http",
        "headers": headers,
        "query_string": b"",
        "path": "/",
        "method": "GET",
        "scheme": "http",
        "server": ("test", 80),
        "client": ("test", 80),
        "root_path": "",
        "http_version": "1.1",
    }
    return Request(scope)


# ──────────────────────────────────────────────
# 5.8 / 5.9 — SSO validation & scopes
# ──────────────────────────────────────────────


def test_demo_pass_through_when_sso_disabled(monkeypatch):
    import api.aigenis.security as s

    monkeypatch.setenv("AIGENIS_ENVIRONMENT", "staging")
    monkeypatch.setenv("AIGENIS_SSO_ENABLED", "0")
    ctx = s.verify_sso_token(_request())
    assert ctx.sub == "opaque-user-id"
    assert ctx.has_scope(s.SCOPE_ANALYTICS_READ)
    assert ctx.has_scope(s.SCOPE_ALERTS_WRITE)


def test_missing_token_in_prod_fails_closed(monkeypatch):
    from fastapi import HTTPException

    import api.aigenis.security as s

    monkeypatch.setenv("AIGENIS_ENVIRONMENT", "production")
    with pytest.raises(HTTPException) as exc:
        s.verify_sso_token(_request())
    assert exc.value.status_code == 401


def test_valid_jwt_creates_sso_context(monkeypatch):
    import api.aigenis.security as s

    private, jwks = _jwks_pair()
    monkeypatch.setenv("AIGENIS_ENVIRONMENT", "production")
    monkeypatch.setattr(s, "_load_jwks", lambda: jwks)

    token = _token(private, _claims(scopes=[s.SCOPE_ANALYTICS_READ, s.SCOPE_PORTFOLIO_READ]))
    ctx = s.verify_sso_token(_request(token=token))
    assert ctx.sub == "u-42"
    assert ctx.tier == "premium"
    assert ctx.has_scope(s.SCOPE_ANALYTICS_READ)
    assert not ctx.has_scope(s.SCOPE_ALERTS_WRITE)


def test_invalid_signature_returns_401(monkeypatch):
    from fastapi import HTTPException

    import api.aigenis.security as s

    private, _ = _jwks_pair()
    _, other_jwks = _jwks_pair()
    monkeypatch.setenv("AIGENIS_ENVIRONMENT", "production")
    monkeypatch.setattr(s, "_load_jwks", lambda: other_jwks)

    token = _token(private, _claims())
    with pytest.raises(HTTPException) as exc:
        s.verify_sso_token(_request(token=token))
    assert exc.value.status_code == 401


def test_expired_token_returns_401(monkeypatch):
    from fastapi import HTTPException

    import api.aigenis.security as s

    private, jwks = _jwks_pair()
    monkeypatch.setenv("AIGENIS_ENVIRONMENT", "production")
    monkeypatch.setattr(s, "_load_jwks", lambda: jwks)

    claims = _claims()
    claims["exp"] = int(time.time()) - 60
    with pytest.raises(HTTPException) as exc:
        s.verify_sso_token(_request(token=_token(private, claims)))
    assert exc.value.status_code == 401


def test_missing_jwks_fails_closed(monkeypatch):
    from fastapi import HTTPException

    import api.aigenis.security as s

    monkeypatch.setenv("AIGENIS_ENVIRONMENT", "production")
    monkeypatch.setattr(s, "_load_jwks", lambda: {"keys": []})
    with pytest.raises(HTTPException) as exc:
        s.verify_sso_token(_request(token="anything"))
    assert exc.value.status_code == 401


def test_require_scope_denies_missing_scope(monkeypatch):
    from fastapi import HTTPException

    import api.aigenis.security as s

    private, jwks = _jwks_pair()
    monkeypatch.setenv("AIGENIS_ENVIRONMENT", "production")
    monkeypatch.setattr(s, "_load_jwks", lambda: jwks)

    token = _token(private, _claims(scopes=[s.SCOPE_ANALYTICS_READ]))
    ctx = s.verify_sso_token(_request(token=token))
    dep = s.require_scope(s.SCOPE_ALERTS_WRITE)
    with pytest.raises(HTTPException) as exc:
        dep(ctx=ctx)
    assert exc.value.status_code == 403


def test_require_scope_allows_present_scope(monkeypatch):
    import api.aigenis.security as s

    private, jwks = _jwks_pair()
    monkeypatch.setenv("AIGENIS_ENVIRONMENT", "production")
    monkeypatch.setattr(s, "_load_jwks", lambda: jwks)

    token = _token(private, _claims(scopes=[s.SCOPE_ALERTS_WRITE]))
    ctx = s.verify_sso_token(_request(token=token))
    dep = s.require_scope(s.SCOPE_ALERTS_WRITE)
    result = dep(ctx=ctx)
    assert result.has_scope(s.SCOPE_ALERTS_WRITE)


# ──────────────────────────────────────────────
# 5.5 — provider contract tests
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_provider_returns_canonical_fixtures():
    from scraper.providers.demo import DemoFixtureProvider

    provider = DemoFixtureProvider()
    bonds = await provider.fetch_bonds("bcse")
    assert len(bonds) >= 1
    assert all(b["internal_id"] for b in bonds)
    assert all(b["market"] == "bcse" for b in bonds)
    assert provider.data_lineage.source == "demo_fixtures"
    assert await provider.health_check() is True


@pytest.mark.asyncio
async def test_moex_provider_inactive_by_default():
    from scraper.providers.moex import MoexProvider

    provider = MoexProvider()
    assert await provider.fetch_bonds("moex") == []
    assert await provider.health_check() is False


@pytest.mark.asyncio
async def test_aigenis_official_inactive_by_default():
    from scraper.providers.aigenis_official import AigenisOfficialProvider

    provider = AigenisOfficialProvider()
    assert await provider.fetch_bonds("bcse") == []
    assert await provider.health_check() is False


def test_registry_default_provider_by_profile(monkeypatch):
    from scraper.providers.registry import _default_provider_name

    monkeypatch.setenv("DEPLOYMENT_PROFILE", "aigenis")
    assert _default_provider_name() == "aigenis_official"

    monkeypatch.setenv("DEPLOYMENT_PROFILE", "saas")
    assert _default_provider_name() == "moex"


def test_fail_closed_in_aigenis_profile(monkeypatch):
    from scraper.providers.registry import (
        ProviderNotConfiguredError,
        assert_browser_scraping_allowed,
    )

    monkeypatch.setenv("DEPLOYMENT_PROFILE", "aigenis")
    monkeypatch.setenv("DATA_SOURCE", "aigenis")
    with pytest.raises(ProviderNotConfiguredError):
        assert_browser_scraping_allowed()

    monkeypatch.setenv("DATA_SOURCE", "moex")
    assert_browser_scraping_allowed()  # не должен бросать


def test_browser_scraping_allowed_outside_aigenis(monkeypatch):
    from scraper.providers.registry import assert_browser_scraping_allowed

    monkeypatch.setenv("DEPLOYMENT_PROFILE", "saas")
    monkeypatch.setenv("DATA_SOURCE", "aigenis")
    assert_browser_scraping_allowed()


# ──────────────────────────────────────────────
# 5.14 — instrument_map DB repository
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_and_resolve_mapping():
    from scraper.db import session_scope
    from scraper.instrument_map import (
        InstrumentMapping,
        resolve_aigenis_id_db,
        resolve_isin_db,
        upsert_mapping_db,
    )

    async with session_scope() as session:
        await upsert_mapping_db(
            session,
            InstrumentMapping(
                aigenis_instrument_id="AIG-1",
                isin="BY0000000001",
                external_ticker="ALFA",
                market="BCSE",
                currency="BYN",
                analytics_internal_id="bond-1",
            ),
        )

    async with session_scope() as session:
        found = await resolve_aigenis_id_db(session, "AIG-1")
        assert found is not None
        assert found.analytics_internal_id == "bond-1"
        assert found.status == "active"

        by_isin = await resolve_isin_db(session, "BY0000000001")
        assert by_isin is not None
        assert by_isin.aigenis_instrument_id == "AIG-1"

        missing = await resolve_aigenis_id_db(session, "NOPE")
        assert missing is None


@pytest.mark.asyncio
async def test_upsert_new_version_increments():
    from scraper.db import session_scope
    from scraper.instrument_map import (
        InstrumentMapping,
        resolve_aigenis_id_db,
        upsert_mapping_db,
    )

    async with session_scope() as session:
        await upsert_mapping_db(
            session,
            InstrumentMapping(
                aigenis_instrument_id="AL-2",
                isin="BY0000000002",
                analytics_internal_id="old-id",
            ),
        )
        await upsert_mapping_db(
            session,
            InstrumentMapping(
                aigenis_instrument_id="AL-2",
                isin="BY0000000002",
                analytics_internal_id="new-id",
            ),
            new_version=True,
        )

    async with session_scope() as session:
        found = await resolve_aigenis_id_db(session, "AL-2")
        assert found is not None
        assert found.analytics_internal_id == "new-id"
        assert found.version >= 2


# ──────────────────────────────────────────────
# 5.6 — snapshot_lineage persistence
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_and_read_latest_lineage():
    from scraper.db import session_scope
    from scraper.lineage import latest_lineage, record_snapshot_lineage

    async with session_scope() as session:
        await record_snapshot_lineage(
            session,
            source="test_source",
            ingestion_run="run-20260806T000000000001",
            quality_status="ok",
            market="bcse",
            rows_processed=42,
            license_contract_id="contract-test",
        )
    async with session_scope() as session:
        row = await latest_lineage(session)
        assert row is not None
        assert row.source == "test_source"
        assert row.ingestion_run == "run-20260806T000000000001"
        assert row.rows_processed == 42
        assert row.license_contract_id == "contract-test"


# ──────────────────────────────────────────────
# Alembic chain (CI "migrations" job runs upgrade head)
# ──────────────────────────────────────────────


def _revision_meta(path: Path) -> tuple[str | None, str | None]:
    import re

    text = path.read_text(encoding="utf-8")
    rev = re.search(
        r'revision\s*:\s*str[^=]*=\s*["\']([^"\']+)["\']|\brevision\s*=\s*["\']([^"\']+)["\']', text
    )
    down = re.search(
        r'down_revision\s*:\s*str[^=]*=\s*["\']([^"\']+)["\']|\bdown_revision\s*=\s*["\']([^"\']+)["\']',
        text,
    )
    return (rev.group(1) or rev.group(2)) if rev else None, (
        down.group(1) or down.group(2)
    ) if down else None


def test_alembic_has_single_head():
    """Alembic должен иметь ровно одну head-ревизию (CI: alembic upgrade head)."""
    import importlib.util

    versions_dir = Path("alembic/versions")
    revisions: dict[str, object] = {}
    for p in versions_dir.glob("*.py"):
        spec = importlib.util.spec_from_file_location(p.stem, p)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, "revision"):
            revisions[mod.revision] = mod.down_revision

    assert revisions, "no alembic revisions found"
    down_refs: set[str] = set()
    for d in revisions.values():
        if isinstance(d, tuple):
            down_refs.update(d)
        elif d:
            down_refs.add(d)
    heads = [r for r in revisions if r not in down_refs]
    assert len(heads) == 1, f"expected single alembic head, got {heads}"


def test_0028_chains_into_main_branch():
    p = Path("alembic/versions/0028_instrument_map.py")
    assert p.exists()
    rev, down = _revision_meta(p)
    assert rev == "0028_instrument_map"
    assert down == "a1b2c3d4e5f6"
    text = p.read_text(encoding="utf-8")
    assert "instrument_map" in text
    assert "snapshot_lineage" in text
