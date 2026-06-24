"""JSON API парсер для истории."""

from __future__ import annotations

from typing import Any

from scraper.api import parse_history_items
from scraper.models import BondHistory


def parse_history_payload(payload: Any, internal_id: str) -> list[BondHistory]:
    items: list[dict[str, Any]] = []
    if isinstance(payload, list):
        items = [it for it in payload if isinstance(it, dict)]
    elif isinstance(payload, dict):
        raw = payload.get("items") or payload.get("data") or payload.get("results")
        if isinstance(raw, list):
            items = [it for it in raw if isinstance(it, dict)]
    return parse_history_items(items, internal_id=internal_id)
