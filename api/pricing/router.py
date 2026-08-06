from __future__ import annotations

import os
import time

from fastapi import APIRouter, Request

from api.billing.service import CURRENCY, PLANS

router = APIRouter(prefix="/pricing", tags=["pricing"])

# Tiny TTL cache for geo lookups: don't block the event loop on every page view.
_geo_cache: dict[str, tuple[float, str]] = {}
_GEO_TTL_SECONDS = 24 * 3600
_GEO_MAX_ENTRIES = 10_000  # bound memory: evict stale entries


def _trusted_proxy() -> bool:
    return os.getenv("TRUSTED_PROXY", "").strip() in ("1", "true", "yes")


def _client_ip(request: Request) -> str | None:
    """Resolve the real client IP without trusting spoofable headers by default.

    ``cf-connecting-ip`` is set by Cloudflare on the demo/proxy path and is
    trusted; ``x-forwarded-for`` / ``x-real-ip`` are only honored when the app
    is explicitly behind a trusted proxy (``TRUSTED_PROXY=1``), mirroring the
    rate limiter in ``api.main``.
    """
    for header in ("cf-connecting-ip", "x-real-ip", "x-forwarded-for"):
        if header != "cf-connecting-ip" and not _trusted_proxy():
            continue
        value = request.headers.get(header, "")
        if value:
            return value.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _is_private_ip(ip: str) -> bool:
    if not ip:
        return True
    for prefix in (
        "192.168.",
        "10.",
        "172.16.",
        "172.17.",
        "172.18.",
        "172.19.",
        "172.20.",
        "172.21.",
        "172.22.",
        "172.23.",
        "172.24.",
        "172.25.",
        "172.26.",
        "172.27.",
        "172.28.",
        "172.29.",
        "172.30.",
        "172.31.",
        "127.",
        "0.",
    ):
        if ip.startswith(prefix):
            return True
    return ip in ("::1", "::ffff:127.0.0.1")


async def _geo_lookup(ip: str) -> str:
    cached = _geo_cache.get(ip)
    if cached and cached[0] + _GEO_TTL_SECONDS > time.time():
        return cached[1]
    # Evict stale entries so the cache stays bounded by distinct IPs per TTL.
    if len(_geo_cache) > _GEO_MAX_ENTRIES:
        cutoff = time.time() - _GEO_TTL_SECONDS
        for key in [k for k, (ts, _) in _geo_cache.items() if ts < cutoff]:
            _geo_cache.pop(key, None)
    country = "US"
    try:
        import httpx

        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                "https://ipapi.co/json/",
                params={"ip": ip},
            )
            data = resp.json()
            country = str(data.get("country_code", "US"))[:2].upper()
    except Exception:
        country = "US"
    _geo_cache[ip] = (time.time(), country)
    return country


async def _detect_country(request: Request) -> str:
    ip = _client_ip(request)
    if not ip or _is_private_ip(ip):
        return "US"
    return await _geo_lookup(ip)


@router.get("/")
async def get_pricing(request: Request):
    country = await _detect_country(request)
    # Prices shown must match what YooKassa actually charges — single source of
    # truth is api.billing.service.PLANS (env-configurable).
    return {
        "pro": float(PLANS["pro"]["price"]),
        "enterprise": float(PLANS["enterprise"]["price"]),
        "currency": CURRENCY,
        "country": country,
        "source": "billing",
    }
