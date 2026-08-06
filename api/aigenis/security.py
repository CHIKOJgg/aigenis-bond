"""
SSO JWT validation and entitlement scopes for the Aigenis integration.

Пункты плана 5.8 (SSO token exchange / BFF pattern) и 5.9 (entitlement
adapter). Реальная валидация JWT:

- Проверка подписи через JWKS URL (AIGENIS_SSO_JWKS_URL) — в production.
- Проверка claims: iss, aud, exp, sub (python-jose).
- Entitlement scopes: analytics:read, portfolio:read, alerts:write.

В demo/staging без SSO-конфигурации используется pass-through контекст
``opaque-user-id``, чтобы презентация работала без подключённого IdP.
В production JWT-валидация обязательна (fail-closed): без валидного токена
эндпоинты возвращают 401.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt

from api.aigenis.audit import audit_event
from scraper.logging import get_logger

logger = get_logger("api.aigenis.security")

SCOPE_ANALYTICS_READ = "analytics:read"
SCOPE_PORTFOLIO_READ = "portfolio:read"
SCOPE_ALERTS_WRITE = "alerts:write"

ALL_SCOPES = {SCOPE_ANALYTICS_READ, SCOPE_PORTFOLIO_READ, SCOPE_ALERTS_WRITE}

_JWT_ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384"]


@dataclass(slots=True)
class SsoContext:
    """Проверенный SSO-контекст запроса (без PII)."""

    sub: str
    tenant: str | None = None
    tier: str | None = None
    scopes: set[str] = field(default_factory=set)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def to_audit(self) -> dict[str, Any]:
        return {
            "tenant": self.tenant,
            "tier": self.tier,
            "scopes": sorted(self.scopes),
        }


def _is_production() -> bool:
    return (os.getenv("AIGENIS_ENVIRONMENT") or "development").lower() in (
        "production",
        "prod",
    )


def _sso_enabled() -> bool:
    if _is_production():
        return True
    return (os.getenv("AIGENIS_SSO_ENABLED", "0").strip() or "").lower() in (
        "1",
        "true",
        "yes",
    )


def _demo_context() -> SsoContext:
    """Pass-through демонстрационный контекст (только вне production)."""
    return SsoContext(
        sub="opaque-user-id",
        tenant="aigenis",
        tier="premium",
        scopes=set(ALL_SCOPES),
    )


@lru_cache(maxsize=1)
def _load_jwks() -> dict[str, Any]:
    """Загрузить и закэшировать JWKS-ключи от IdP.

    Пустой набор ключей => подпись проверить нельзя => fail-closed.
    """
    import httpx

    jwks_url = os.environ.get("AIGENIS_SSO_JWKS_URL", "").strip()
    if not jwks_url:
        logger.warning("sso_jwks_not_configured")
        return {"keys": []}
    try:
        resp = httpx.get(jwks_url, timeout=10)
        resp.raise_for_status()
        keys = list(resp.json().get("keys", []))
        logger.info("sso_jwks_loaded", keys=len(keys), source=jwks_url)
        return {"keys": keys}
    except Exception as exc:  # pragma: no cover - сетевой сбой => fail-closed
        logger.error("sso_jwks_load_failed", error=str(exc))
        return {"keys": []}


def _extract_scopes(claims: dict[str, Any]) -> set[str]:
    raw = claims.get("scope") or claims.get("scopes") or []
    if isinstance(raw, str):
        return {s.strip() for s in raw.split() if s.strip()}
    if isinstance(raw, list):
        return {str(s).strip() for s in raw if str(s).strip()}
    return set()


def _validate_jwt(token: str) -> dict[str, Any]:
    """Валидация подписи и обязательных claims (iss/aud/exp/sub)."""
    issuer = os.environ.get("AIGENIS_SSO_ISSUER", "").strip() or None
    audience = os.environ.get("AIGENIS_SSO_AUDIENCE", "").strip() or None
    jwks = _load_jwks()
    if not jwks.get("keys"):
        raise HTTPException(401, "SSO not configured: no JWKS keys")
    try:
        claims = jwt.decode(
            token,
            jwks,
            algorithms=_JWT_ALGORITHMS,
            audience=audience,
            issuer=issuer,
            options={
                "require_exp": True,
                "verify_aud": audience is not None,
                "verify_iss": issuer is not None,
            },
        )
    except JWTError as exc:
        audit_event("sso_validation_failed", extra={"error": str(exc)})
        raise HTTPException(401, "Invalid or expired token") from exc
    if not claims.get("sub"):
        raise HTTPException(401, "Token missing sub claim")
    return dict(claims)


def verify_sso_token(request: Request) -> SsoContext:
    """FastAPI-зависимость: проверяет SSO JWT и возвращает entitlement-контекст.

    - В production требует валидный Bearer-токен (fail-closed).
    - В demo/staging без AIGENIS_SSO_ENABLED возвращает pass-through контекст.
    """
    authorization = request.headers.get("Authorization", "")
    if not authorization.lower().startswith("bearer "):
        if not _sso_enabled():
            audit_event("sso_pass_through")
            return _demo_context()
        audit_event("sso_missing_token")
        raise HTTPException(401, "Missing Authorization header")

    token = authorization.split(" ", 1)[1].strip()
    if not _sso_enabled():
        audit_event("sso_pass_through")
        return _demo_context()

    claims = _validate_jwt(token)
    ctx = SsoContext(
        sub=str(claims.get("sub", "")),
        tenant=str(claims["tenant"]) if claims.get("tenant") else None,
        tier=str(claims["tier"]) if claims.get("tier") else None,
        scopes=_extract_scopes(claims),
    )
    audit_event("sso_authenticated", user_id=ctx.sub, extra=ctx.to_audit())
    return ctx


def require_scope(scope: str) -> Any:
    """Фабрика FastAPI-зависимости: требует наличие scope в SSO-контексте."""

    def dependency(ctx: SsoContext = Depends(verify_sso_token)) -> SsoContext:
        if scope not in ctx.scopes:
            audit_event("sso_scope_denied", user_id=ctx.sub, extra={"scope": scope})
            raise HTTPException(403, f"Missing required scope: {scope}")
        return ctx

    return dependency
