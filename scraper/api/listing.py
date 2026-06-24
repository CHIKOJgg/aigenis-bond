"""JSON API парсер для листинга."""

from __future__ import annotations

from typing import Any

from scraper.api import parse_listing_items


def parse_listing_payload(payload: Any, currency: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return parse_listing_items(payload, currency)
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("data") or payload.get("results")
        if isinstance(items, list):
            return parse_listing_items(items, currency)
    return []
