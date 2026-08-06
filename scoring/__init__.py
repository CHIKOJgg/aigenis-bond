"""Scoring модуль: Reward/Risk Score v2 для облигаций Aigenis."""

from __future__ import annotations

from scoring.data_quality import (
    DataQualityResult,
    score_bond_safe,
    validate_bond_data,
)
from scoring.engine import (
    CURRENCY_BONUS,
    METAL_EXTRA_BONUS,
    _classify_issuer,
    score_bond,
    score_bonds,
)
from scoring.models import BondScore, ScoreBreakdown

__all__ = [
    "CURRENCY_BONUS",
    "METAL_EXTRA_BONUS",
    "BondScore",
    "DataQualityResult",
    "ScoreBreakdown",
    "_classify_issuer",
    "score_bond",
    "score_bond_safe",
    "score_bonds",
    "validate_bond_data",
]
