"""JSON API парсер для детальной страницы."""

from __future__ import annotations

from typing import Any

from scraper.api import parse_bond_payload
from scraper.models import Bond


def parse_detail_payload(payload: Any, internal_id: str) -> Bond:
    if not isinstance(payload, dict):
        raise ValueError("detail payload must be object")
    return parse_bond_payload(payload, internal_id_fallback=internal_id)
