"""Scoring модуль: Reward/Risk Score для облигаций Aigenis."""

from __future__ import annotations

from scoring.engine import (
    CURRENCY_BONUS,
    METAL_EXTRA_BONUS,
    score_bond,
    score_bonds,
)
from scoring.models import BondScore, ScoreBreakdown

__all__ = [
    "BondScore",
    "ScoreBreakdown",
    "CURRENCY_BONUS",
    "METAL_EXTRA_BONUS",
    "score_bond",
    "score_bonds",
]
