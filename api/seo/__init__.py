"""Public, server-rendered SEO pages (split from the former api/seo.py module).

Router lives here so that ``from api.seo import router`` keeps working (used by
api/main.py and tests). ``regenerate_sitemap`` is re-exported for
scraper/__main__.py and scraper/scheduler.py.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["seo"])

from api.seo import calculator, guides, pages, partners  # noqa: E402,F401
from api.seo.pages import regenerate_sitemap  # noqa: E402,F401
