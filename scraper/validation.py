from __future__ import annotations

from decimal import Decimal
from typing import Any

from scraper.errors import ValidationError as ScraperValidationError

_REQUIRED_DETAIL = {"name", "currency"}
_REQUIRED_DETAIL_IDS = {"id", "internal_id"}
_REQUIRED_LISTING = {"internal_id", "name", "currency"}


def validate_detail(data: dict[str, Any]) -> dict[str, Any]:
    missing = _REQUIRED_DETAIL - set(data.keys())
    if missing:
        raise ScraperValidationError(
            f"detail missing required fields: {missing}", context={"missing": list(missing)}
        )
    if not (_REQUIRED_DETAIL_IDS & set(data.keys())):
        raise ScraperValidationError("detail missing id or internal_id")
    ytm = data.get("yield_to_maturity")
    if ytm is not None:
        try:
            Decimal(str(ytm))
        except Exception as exc:
            raise ScraperValidationError(f"invalid yield_to_maturity: {ytm!r}", cause=exc) from exc
    price = data.get("price")
    if price is not None:
        try:
            Decimal(str(price))
        except Exception as exc:
            raise ScraperValidationError(f"invalid price: {price!r}", cause=exc) from exc
    return data


def validate_listing_item(item: dict[str, Any]) -> dict[str, Any]:
    missing = _REQUIRED_LISTING - set(item.keys())
    if missing:
        raise ScraperValidationError(
            f"listing item missing required fields: {missing}", context={"missing": list(missing)}
        )
    return item


def validate_listing(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [validate_listing_item(it) for it in items]
