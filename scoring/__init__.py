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
    "CURRENCY_BONUS",
    "METAL_EXTRA_BONUS",
    "BondScore",
    "ScoreBreakdown",
    "score_bond",
    "score_bonds",
]
