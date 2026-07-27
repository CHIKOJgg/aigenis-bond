from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/pricing", tags=["pricing"])

PRICES = {
    "BYN": {"pro": 29.0, "enterprise": 99.0, "currency": "BYN"},
    "RUB": {"pro": 2500.0, "enterprise": 8500.0, "currency": "RUB"},
    "USD": {"pro": 25.0, "enterprise": 85.0, "currency": "USD"},
}

COUNTRY_MAP = {
    "BY": "BYN",
    "RU": "RUB",
}


def _detect_country(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    x_real_ip = request.headers.get("x-real-ip", "")
    cf_ip = request.headers.get("cf-connecting-ip", "")
    for header in (cf_ip, x_real_ip, forwarded):
        if header:
            ip = header.split(",")[0].strip()
            if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
                continue
            return _geo_lookup(ip)
    return "USD"


def _geo_lookup(ip: str) -> str:
    try:
        import httpx

        with httpx.Client(timeout=3.0) as client:
            resp = client.get(
                "https://ipapi.co/json/",
                params={"ip": ip},
            )
            data = resp.json()
            country = data.get("country_code", "US")
    except Exception:
        country = "US"
    return COUNTRY_MAP.get(country, "USD")


@router.get("/")
async def get_pricing(request: Request):
    country = _detect_country(request)
    prices = PRICES[country]
    return {
        "pro": prices["pro"],
        "enterprise": prices["enterprise"],
        "currency": prices["currency"],
        "country": country,
        "source": "ip-detection",
    }