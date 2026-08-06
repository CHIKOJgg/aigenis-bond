"""Locating the built SPA (frontend ``dist/``) for backend-served pages.

The FastAPI backend serves both the API and the production frontend build.
Both ``api/main.py`` (static assets + SPA fallback) and ``api/seo.py``
(bot/human split on SEO-covered paths) need the same lookup, so it lives here.
"""

from __future__ import annotations

import os
from pathlib import Path


def frontend_dir() -> Path | None:
    """Absolute path of the built frontend directory (``FRONTEND_DIR``)."""
    d = os.environ.get("FRONTEND_DIR", "").strip()
    if d and os.path.isdir(d):
        return Path(d)
    return None


def frontend_index() -> Path | None:
    """Path of the SPA entry file (``dist/index.html``), if built."""
    root = frontend_dir()
    if root is None:
        return None
    index = root / "index.html"
    return index if index.is_file() else None
