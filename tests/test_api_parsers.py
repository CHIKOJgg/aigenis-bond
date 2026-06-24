"""Тесты API-парсеров."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from scraper.api.detail import parse_detail_payload
from scraper.api.history import parse_history_payload
from scraper.api.listing import parse_listing_payload


@pytest.fixture
def listing_payload(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "listing.json").read_text(encoding="utf-8"))


@pytest.fixture
def detail_payload(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "detail.json").read_text(encoding="utf-8"))


@pytest.fixture
def history_payload(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir / "history.json").read_text(encoding="utf-8"))


def test_listing_payload(listing_payload: dict) -> None:
    items = parse_listing_payload(listing_payload, "USD")
    assert len(items) == 3
    assert items[0]["internal_id"] == "OP-51"
    assert items[0]["currency"] == "USD"
    assert items[1]["isin"] is None


def test_detail_payload(detail_payload: dict) -> None:
    bond = parse_detail_payload(detail_payload, "OP-51")
    assert bond.internal_id == "OP-51"
    assert bond.currency == "USD"
    assert bond.nominal == Decimal("1000")
    assert bond.maturity_date == date(2030, 6, 15)
    assert bond.yield_to_maturity == Decimal("5.47")


def test_history_payload(history_payload: dict) -> None:
    rows = parse_history_payload(history_payload, "OP-51")
    assert len(rows) == 3
    assert rows[0].date == date(2026, 6, 1)
    assert rows[0].yield_ == Decimal("5.6")
    assert rows[0].internal_id == "OP-51"
