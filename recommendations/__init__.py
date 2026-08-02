"""Recommendations: объединение Score + ML + пользовательских предпочтений."""

from __future__ import annotations

from recommendations.engine import recommend_bonds, recommend_for_issuer

__all__ = ["recommend_bonds", "recommend_for_issuer"]
