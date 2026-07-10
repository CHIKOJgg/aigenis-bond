"""Tests for the subscription / tier logic (no DB or network required)."""
from __future__ import annotations

from telegram_bot import subscriptions as s


def test_star_plans_well_formed():
    assert set(s.STAR_PLANS) == {"pro", "enterprise"}
    for plan in s.STAR_PLANS.values():
        assert plan.stars > 0
        assert plan.duration_days > 0
        assert plan.tier in ("pro", "enterprise")


def test_tier_ranking_and_meets():
    assert s.tier_rank("free") < s.tier_rank("pro") < s.tier_rank("enterprise")
    assert s.meets_tier("free", "free")
    assert not s.meets_tier("free", "pro")
    assert s.meets_tier("pro", "pro")
    assert s.meets_tier("enterprise", "pro")
    assert not s.meets_tier("pro", "enterprise")


def test_is_paid():
    assert not s.is_paid("free")
    assert s.is_paid("pro")
    assert s.is_paid("enterprise")


def test_env_overrides_stars_amounts(monkeypatch):
    monkeypatch.setenv("STARS_PRO", "199")
    # Reload the module so the new env value is picked up.
    import importlib

    importlib.reload(s)
    assert s.STAR_PLANS["pro"].stars == 199
