"""Tests for API subscription gating (no DB / network required)."""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from api import access_control as ac


def test_require_feature_allows_paid_tier():
    dep = ac.RequireFeature("access_desk_rv")
    # pro tier has the flag -> no exception
    assert asyncio.run(dep(tier="pro")) is None
    assert asyncio.run(dep(tier="enterprise")) is None


def test_require_feature_blocks_free_tier():
    dep = ac.RequireFeature("access_desk_rv")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dep(tier="free"))
    assert exc.value.status_code == 402


def test_feature_flags_present_for_every_tier():
    # Every access_* flag referenced by the analytics router must exist for all tiers.
    required = {
        "access_desk_rv",
        "access_desk_carry",
        "access_desk_repo",
        "access_desk_curve",
        "access_desk_stress",
        "access_recommendations",
        "access_ml",
        "access_alerts",
        "access_portfolio",
        "access_forecast",
    }
    for tier, flags in ac.FEATURE_FLAGS.items():
        missing = required - set(flags)
        assert not missing, f"tier {tier} missing flags: {missing}"


def test_free_tier_has_no_paid_flags():
    free = ac.FEATURE_FLAGS["free"]
    assert not free.get("access_desk_rv")
    assert not free.get("access_portfolio")
