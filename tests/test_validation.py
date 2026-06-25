from __future__ import annotations

import pytest

from scraper.errors import ValidationError
from scraper.validation import validate_detail, validate_listing, validate_listing_item


def test_validate_detail_valid():
    data = {"name": "Test Bond", "currency": "USD", "id": "OP-1"}
    result = validate_detail(data)
    assert result["name"] == "Test Bond"


def test_validate_detail_missing_required():
    with pytest.raises(ValidationError, match="missing required fields"):
        validate_detail({"currency": "USD"})


def test_validate_detail_missing_id():
    with pytest.raises(ValidationError, match="missing id or internal_id"):
        validate_detail({"name": "Test", "currency": "USD"})


def test_validate_detail_invalid_ytm():
    with pytest.raises(ValidationError):
        validate_detail(
            {"name": "Test", "currency": "USD", "id": "OP-1", "yield_to_maturity": "invalid"}
        )


def test_validate_detail_invalid_price():
    with pytest.raises(ValidationError):
        validate_detail({"name": "Test", "currency": "USD", "id": "OP-1", "price": "bad"})


def test_validate_listing_item_valid():
    item = {"internal_id": "OP-1", "name": "Test", "currency": "USD"}
    result = validate_listing_item(item)
    assert result["internal_id"] == "OP-1"


def test_validate_listing_item_missing():
    with pytest.raises(ValidationError):
        validate_listing_item({"name": "Test"})


def test_validate_listing_all():
    items = [
        {"internal_id": "OP-1", "name": "A", "currency": "USD"},
        {"internal_id": "OP-2", "name": "B", "currency": "BYN"},
    ]
    result = validate_listing(items)
    assert len(result) == 2
