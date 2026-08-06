"""Analytics API package (split from the former api/analytics.py module).

Router lives here so that ``from api.analytics import router`` keeps working.
`_get_bond_or_404` / `_score_for_bond` are re-exported for api/partner/router.py.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["analytics"])

from api.analytics import bonds, desk, insights, portfolio  # noqa: E402,F401
from api.analytics._helpers import (  # noqa: E402,F401
    _get_bond_or_404,
    _score_for_bond,
)
