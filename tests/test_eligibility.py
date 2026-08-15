"""Tests for scoring/eligibility.py — Portfolio Eligibility Gate.

Дистрибуция, сверхвысокорисковые активы и аномалии доходности не должны
попадать в портфель ни при какой стратегии.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from portfolio.optimizer import rank_bonds
from scoring.eligibility import (
    check_eligibility,
    filter_eligible,
    peer_ytms_by_currency,
)
from scraper.models import Bond


def _make_bond(
    internal_id: str,
    *,
    ytm: float | None = 10.0,
    price: float | None = 100.0,
    currency: str = "USD",
    status: str = "active",
) -> Bond:
    return Bond(
        internal_id=internal_id,
        name=f"Bond {internal_id}",
        issuer="Treasury",
        currency=currency,  # type: ignore[arg-type]
        coupon_rate=Decimal("10"),
        coupon_frequency=2,  # type: ignore[arg-type]
        maturity_date=date(2035, 1, 1),
        price=Decimal(str(price)) if price is not None else None,
        yield_to_maturity=Decimal(str(ytm)) if ytm is not None else None,
        status=status,  # type: ignore[arg-type]
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


# =========================================================================== #
# check_eligibility
# =========================================================================== #


def test_healthy_bond_eligible():
    res = check_eligibility(
        internal_id="OK-1",
        price_pct=100.0,
        ytm_pct=10.0,
        status="active",
    )
    assert res.eligible is True
    assert res.reason is None


def test_distribution_condition_blocks():
    """Цена < 80% номинала при YTM > 30% — «Дистрибуция / вероятность дефолта»."""
    res = check_eligibility(
        internal_id="DIST-1",
        price_pct=55.0,
        ytm_pct=57.6,
        status="active",
    )
    assert res.eligible is False
    assert res.kind == "distribution"
    assert "Дистрибуция" in (res.reason or "")


def test_low_price_with_normal_ytm_is_eligible():
    """Только цена < 80% без высокой доходности — не дистрибуция."""
    res = check_eligibility(
        internal_id="LOW-1",
        price_pct=70.0,
        ytm_pct=10.0,
        status="active",
    )
    assert res.eligible is True


def test_high_ytm_with_normal_price_is_eligible():
    """Только YTM > 30% без цены < 80% — не дистрибуция (высокий купон)."""
    res = check_eligibility(
        internal_id="HI-1",
        price_pct=95.0,
        ytm_pct=45.0,
        status="active",
    )
    assert res.eligible is True


def test_extreme_ytm_blocks():
    """YTM > 100% — аномалия данных или экстремальный дистресс (1545%, 800%)."""
    for ytm in (1545.29, 800.55, 306.74, 101.0):
        res = check_eligibility(
            internal_id=f"EXT-{ytm}",
            price_pct=90.0,
            ytm_pct=ytm,
            status="active",
        )
        assert res.eligible is False
        assert res.kind == "extreme_risk"


def test_extreme_low_price_blocks():
    res = check_eligibility(
        internal_id="EXT-PRICE",
        price_pct=25.0,
        ytm_pct=5.0,
        status="active",
    )
    assert res.eligible is False
    assert res.kind == "extreme_risk"


def test_status_blocked():
    for status in ("defaulted", "bankrupt", "suspended", "delisted", "matured"):
        res = check_eligibility(
            internal_id=f"ST-{status}",
            price_pct=100.0,
            ytm_pct=10.0,
            status=status,
        )
        assert res.eligible is False
        assert res.kind == "status"


def test_anomaly_high_ytm_vs_peers_blocks():
    """«Обычная» бумага с YTM 57.6% при аналогах 4-15% — аномалия."""
    peers = [4.0, 6.0, 8.0, 10.0, 12.0, 15.0]
    res = check_eligibility(
        internal_id="ANOM-1",
        price_pct=99.0,
        ytm_pct=57.6,
        status="active",
        peer_ytms=peers,
    )
    assert res.eligible is False
    assert res.kind == "anomaly"
    assert "Аномалия" in (res.reason or "")


def test_low_ytm_not_flagged_as_anomaly():
    """Проверка односторонняя: низкая доходность (суверенные) — не аномалия."""
    peers = [4.0, 6.0, 8.0, 10.0, 12.0, 15.0]
    res = check_eligibility(
        internal_id="GOV-1",
        price_pct=100.0,
        ytm_pct=1.0,
        status="active",
        peer_ytms=peers,
    )
    assert res.eligible is True


def test_anomaly_robust_to_outlier_in_peers():
    """Один выброс (1545%) в аналогах не раздувает разброс (MAD-робастность)."""
    peers = [4.0, 6.0, 8.0, 10.0, 12.0, 1500.0]
    res = check_eligibility(
        internal_id="OK-2",
        price_pct=100.0,
        ytm_pct=20.0,
        status="active",
        peer_ytms=peers,
    )
    assert res.eligible is True


def test_anomaly_needs_enough_peers():
    """Меньше 5 аналогов — аномалию не детектируем (нет базы)."""
    res = check_eligibility(
        internal_id="FEW-1",
        price_pct=100.0,
        ytm_pct=57.6,
        status="active",
        peer_ytms=[4.0, 6.0, 8.0],
    )
    assert res.eligible is True


def test_missing_price_and_ytm_eligible():
    res = check_eligibility(internal_id="NONE-1", status="active")
    assert res.eligible is True


# =========================================================================== #
# filter_eligible (dict'ы и объекты)
# =========================================================================== #


def test_filter_eligible_with_dicts():
    bonds = [
        {
            "internal_id": "A1",
            "name": "OK",
            "price": 100.0,
            "nominal": None,
            "yield_to_maturity": 10.0,
            "status": "active",
            "currency": "USD",
        },
        {
            "internal_id": "A2",
            "name": "DIST",
            "price": 55.0,
            "nominal": None,
            "yield_to_maturity": 57.6,
            "status": "active",
            "currency": "USD",
        },
        {
            "internal_id": "A3",
            "name": "EXT",
            "price": 90.0,
            "nominal": None,
            "yield_to_maturity": 800.0,
            "status": "active",
            "currency": "USD",
        },
    ]
    eligible, excluded = filter_eligible(bonds)
    assert [b["internal_id"] for b in eligible] == ["A1"]
    assert set(excluded) == {"A2", "A3"}
    assert excluded["A2"].kind == "distribution"
    assert excluded["A3"].kind == "extreme_risk"


def test_filter_eligible_with_objects_and_peers():
    healthy = _make_bond("H1", ytm=10.0)
    anomaly = _make_bond("AN1", ytm=57.6, price=99.0)
    peers = [
        _make_bond("P1", ytm=4.0),
        _make_bond("P2", ytm=6.0),
        _make_bond("P3", ytm=8.0),
        _make_bond("P4", ytm=10.0),
        _make_bond("P5", ytm=12.0),
    ]
    eligible, excluded = filter_eligible([healthy, anomaly], peer_bonds=peers)
    assert [b.internal_id for b in eligible] == ["H1"]
    assert excluded["AN1"].kind == "anomaly"


def test_peer_ytms_by_currency():
    bonds = [
        _make_bond("B1", ytm=10.0, currency="USD"),
        _make_bond("B2", ytm=5.0, currency="BYN"),
        _make_bond("B3", ytm=None, currency="USD"),
    ]
    peers = peer_ytms_by_currency(bonds)
    assert peers == {"USD": [10.0], "BYN": [5.0]}


# =========================================================================== #
# Интеграция: optimizer rank_bonds
# =========================================================================== #


def test_rank_bonds_excludes_distribution_and_extreme():
    healthy = _make_bond("R-OK", ytm=10.0)
    distribution = _make_bond("R-DIST", ytm=57.6, price=55.0)
    extreme = _make_bond("R-EXT", ytm=800.0, price=50.0)
    ranked = rank_bonds([healthy, distribution, extreme], "Balanced")
    ids = {s.internal_id for s in ranked}
    assert "R-OK" in ids
    assert "R-DIST" not in ids
    assert "R-EXT" not in ids


def test_rank_bonds_excludes_ytm_anomaly():
    healthy = _make_bond("R2-OK", ytm=10.0)
    peers = [_make_bond(f"R2-P{i}", ytm=y) for i, y in enumerate([4.0, 6.0, 8.0, 12.0, 15.0])]
    anomaly = _make_bond("R2-AN", ytm=57.6, price=99.0)
    ranked = rank_bonds([healthy, anomaly, *peers], "Balanced")
    ids = {s.internal_id for s in ranked}
    assert "R2-OK" in ids
    assert "R2-AN" not in ids
