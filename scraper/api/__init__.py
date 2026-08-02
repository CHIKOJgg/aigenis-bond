"""JSON API парсеры (aigenis.by) — maintained at ``scraper.sources.aigenis.api``.

This module re-exports for backward compatibility.
New code should import directly from ``scraper.sources.aigenis.api``.
"""
from __future__ import annotations

from scraper.sources.aigenis.api import (  # noqa: F401
    _coerce_date,
    _first_not_none,
    parse_bond_payload,
    parse_history_items,
    parse_listing_items,
)
