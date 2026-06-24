"""Recommendations: объединение Score + ML + пользовательских предпочтений."""

from __future__ import annotations

from recommendations.engine import recommend_bonds, save_predictions_to_db

__all__ = ["recommend_bonds", "save_predictions_to_db"]
