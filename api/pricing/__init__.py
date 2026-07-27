from __future__ import annotations

from api.access_control import FEATURE_FLAGS

_PLAN_PRICES = {
    "free": 0,
    "pro": 2900,
    "enterprise": 9900,
}

PLANS = {
    tier: {
        "name": tier,
        "tier": tier,
        "price": _PLAN_PRICES[tier],
    }
    for tier in ("free", "pro", "enterprise")
    if tier in FEATURE_FLAGS
}


async def get_available_plans() -> list[dict]:
    tiers_with_popular = {"free": False, "pro": True, "enterprise": False}
    return [
        {
            "name": tier,
            "tier": tier,
            "price": _PLAN_PRICES[tier],
            "popular": tiers_with_popular.get(tier, False),
            "features": list(FEATURE_FLAGS[tier].keys()),
            "api_rate_limit": FEATURE_FLAGS[tier].get("api_rate_limit", 10),
            "max_currencies": FEATURE_FLAGS[tier].get("max_currencies", 1),
        }
        for tier in ("free", "pro", "enterprise")
        if tier in FEATURE_FLAGS
    ]


async def calculate_upgrade_cost(from_tier: str, to_tier: str) -> dict:
    if from_tier not in _PLAN_PRICES or to_tier not in _PLAN_PRICES:
        raise KeyError(f"Unknown tier: {from_tier} or {to_tier}")
    from_price = _PLAN_PRICES[from_tier]
    to_price = _PLAN_PRICES[to_tier]
    difference = to_price - from_price
    return {
        "from": from_tier,
        "to": to_tier,
        "upgrade": difference > 0,
        "difference": max(0, difference),
        "price_change": max(0, difference),
    }
