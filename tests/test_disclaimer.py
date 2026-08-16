"""Tests for scoring.disclaimer (mandatory analytics disclaimers)."""

from __future__ import annotations

from scoring.disclaimer import (
    DISCLAIMER_FULL,
    DISCLAIMER_FULL_EN,
    DISCLAIMER_SHORT,
)


def test_disclaimer_short_non_empty_and_warns():
    assert "не является" in DISCLAIMER_SHORT.lower() or "индивидуальной" in DISCLAIMER_SHORT
    assert DISCLAIMER_SHORT.startswith("⚠️")


def test_disclaimer_full_russian_mentions_not_advice():
    assert "НЕ является индивидуальной" in DISCLAIMER_FULL
    assert "инвестиционной рекомендацией" in DISCLAIMER_FULL


def test_disclaimer_full_en_mentions_not_advice():
    assert "NOT individual investment advice" in DISCLAIMER_FULL_EN
    assert "licensed advisor" in DISCLAIMER_FULL_EN


def test_disclaimer_constants_distinct():
    assert DISCLAIMER_FULL != DISCLAIMER_SHORT
    assert DISCLAIMER_FULL_EN != DISCLAIMER_FULL
