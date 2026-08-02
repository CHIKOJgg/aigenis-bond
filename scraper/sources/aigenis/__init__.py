"""Aigenis.by data source — paid, requires credentials.

This module provides the ``AigenisClient`` which uses Playwright to log in
to the aigenis.by website and scrape bond data via API and HTML fallback.

Enable via ``DATA_SOURCE=aigenis`` or ``DATA_SOURCE=both``.
"""

from __future__ import annotations

AVAILABLE = True
