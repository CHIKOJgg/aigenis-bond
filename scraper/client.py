"""Aigenis.by data source — maintained at ``scraper.sources.aigenis.client``.

This module re-exports from ``scraper.sources.aigenis.client`` for backward
compatibility. New code should import directly from that location.
"""

from __future__ import annotations

from scraper.sources.aigenis.client import (  # noqa: F401
    AigenisClient,
    _abs_url,
    aigenis_client,
)
