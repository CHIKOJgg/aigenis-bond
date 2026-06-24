"""Валидация данных облигаций после парсинга."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

_REQUIRED_DETAIL = {"name", "currency"}
_REQUIRED_DETAIL_IDS = {"id", "internal_id"}
_REQUIRED_LISTING = {"internal_id", "name", "currency"}


def validate_detail(data: dict[str, Any]) -> dict[str, Any]:
    missing = _REQUIRED_DETAIL - set(data.keys())
    if missing:
        raise ValueError(f"detail missing required fields: {missing}")
    if not (_REQUIRED_DETAIL_IDS & set(data.keys())):
        raise ValueError(f"detail missing id or internal_id")
    ytm = data.get("yield_to_maturity")
    if ytm is not None:
        try:
            Decimal(str(ytm))
        except Exception as exc:
            raise ValueError(f"invalid yield_to_maturity: {ytm!r}") from exc
    price = data.get("price")
    if price is not None:
        try:
            Decimal(str(price))
        except Exception as exc:
            raise ValueError(f"invalid price: {price!r}") from exc
    return data


def validate_listing_item(item: dict[str, Any]) -> dict[str, Any]:
    missing = _REQUIRED_LISTING - set(item.keys())
    if missing:
        raise ValueError(f"listing item missing required fields: {missing}")
    return item


def validate_listing(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [validate_listing_item(it) for it in items]
