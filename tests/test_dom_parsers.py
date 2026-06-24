"""Тесты DOM-парсеров на зафиксированных снэпшотах."""

from __future__ import annotations

from pathlib import Path

from scraper.parsers.detail import parse_detail_html
from scraper.parsers.history import parse_history_html
from scraper.parsers.listing import parse_listing_html


def test_listing_html(fixtures_dir: Path) -> None:
    html = (fixtures_dir / "listing.html").read_text(encoding="utf-8")
    items = parse_listing_html(html, currency="USD")
    ids = [it["internal_id"] for it in items]
    # Парсер использует data-reg (номер регистрации) как internal_id
    assert len(ids) >= 2
    assert all(isinstance(i, str) and len(i) > 0 for i in ids)


def test_detail_html(fixtures_dir: Path) -> None:
    html = (fixtures_dir / "detail.html").read_text(encoding="utf-8")
    payload = parse_detail_html(html, internal_id="OP-51")
    assert payload["id"] == "OP-51"
    assert payload["name"]
    assert payload["currency"].lower() in {"usd", "доллар", "доллар сша"}
    assert payload["coupon_rate"]


def test_history_html(fixtures_dir: Path) -> None:
    html = """
    <html><body><table class='history'>
        <tbody>
            <tr><td>2026-06-01</td><td>97.8</td><td>5.6</td><td>5.25</td><td>active</td></tr>
            <tr><td>2026-06-02</td><td>98.0</td><td>5.55</td><td>5.25</td><td>active</td></tr>
        </tbody>
    </table></body></html>
    """
    rows = parse_history_html(html, internal_id="OP-51")
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-06-01"
