"""Unit tests for feature access-control gating and pricing plans.

Covers: tier->feature flags, the RequireFeature dependency's 402 decision,
per-tier API rate-limit values, and pricing plan math.
"""
from __future__ import annotations

import pytest

import api.access_control as ac
from api.access_control import FEATURE_FLAGS, RequireFeature
from api.pricing import PLANS, calculate_upgrade_cost, get_available_plans


# --------------------------------------------------------------------------- #
# Feature flags per tier
# --------------------------------------------------------------------------- #
def test_feature_flags_present_for_all_tiers():
    for tier in ("free", "pro", "enterprise"):
        assert tier in FEATURE_FLAGS
        # Every tier must at least allow the free market endpoints.
        assert FEATURE_FLAGS[tier]["access_bond_list"] is True
        assert FEATURE_FLAGS[tier]["access_scores"] is True


def test_pro_features_locked_for_free():
    free = FEATURE_FLAGS["free"]
    assert free["access_portfolio"] is False
    assert free["access_desk_rv"] is False
    assert free["access_ml"] is False
    # Pro unlocks them.
    pro = FEATURE_FLAGS["pro"]
    assert pro["access_portfolio"] is True
    assert pro["access_desk_rv"] is True
    assert pro["access_ml"] is True


def test_api_rate_limits_increase_by_tier():
    assert FEATURE_FLAGS["free"]["api_rate_limit"] < FEATURE_FLAGS["pro"]["api_rate_limit"]
    assert FEATURE_FLAGS["pro"]["api_rate_limit"] < FEATURE_FLAGS["enterprise"]["api_rate_limit"]


# --------------------------------------------------------------------------- #
# RequireFeature gating decision
# --------------------------------------------------------------------------- #
def test_require_feature_allows_pro():
    import asyncio

    async def run():
        dep = RequireFeature("access_portfolio")
        await dep(tier="pro")  # no exception

    asyncio.run(run())


def test_require_feature_blocks_free():
    import asyncio

    from fastapi import HTTPException

    async def run():
        dep = RequireFeature("access_portfolio")
        with pytest.raises(HTTPException) as exc:
            await dep(tier="free")
        assert exc.value.status_code == 402
        assert exc.value.headers.get("X-Upgrade-Required") == "true"

    asyncio.run(run())


def test_require_feature_unknown_tier_falls_back_to_free():
    import asyncio

    from fastapi import HTTPException

    async def run():
        dep = RequireFeature("access_portfolio")
        with pytest.raises(HTTPException):
            await dep(tier="does-not-exist")

    asyncio.run(run())


# --------------------------------------------------------------------------- #
# Pricing plans
# --------------------------------------------------------------------------- #
def test_plans_include_all_tiers():
    plans = PLANS
    assert set(plans) == {"free", "pro", "enterprise"}
    assert plans["free"]["price"] == 0
    assert plans["pro"]["price"] == 2900
    assert plans["enterprise"]["price"] == 9900


def test_get_available_plans_shape():
    import asyncio

    result = asyncio.run(get_available_plans())
    assert len(result) == 3
    assert any(p["popular"] for p in result)  # pro is popular


def test_calculate_upgrade_cost_same_plan():
    import asyncio

    res = asyncio.run(calculate_upgrade_cost("pro", "pro"))
    assert res["upgrade"] is False
    assert res["difference"] == 0


def test_calculate_upgrade_cost_pro_to_enterprise():
    import asyncio

    res = asyncio.run(calculate_upgrade_cost("pro", "enterprise"))
    assert res["upgrade"] is True
    assert res["difference"] == 9900 - 2900
    assert res["price_change"] == res["difference"]


def test_calculate_upgrade_cost_unknown_plan_raises():
    import asyncio

    with pytest.raises(KeyError):
        asyncio.run(calculate_upgrade_cost("pro", "ultra"))
