"""Tests for scoring/data_quality.py — gate that ensures scoring never lies."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from scoring.data_quality import (
    MAX_DATA_AGE_HOURS,
    score_bond_safe,
    validate_bond_data,
)


def test_valid_bond_passes_all_checks():
    dq = validate_bond_data(
        internal_id="TEST-1",
        yield_to_maturity=12.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=8.0,
        fetched_at=datetime.now(UTC) - timedelta(hours=1),
        isin="US1234567890",
    )
    assert dq.overall == "ok"
    assert dq.is_rated
    assert dq.confidence == "high"
    assert len(dq.issues) == 0


def test_missing_id_is_critical():
    dq = validate_bond_data(
        internal_id="",
        yield_to_maturity=10.0,
        currency="USD",
        maturity_date=None,
        status="active",
        issuer=None,
        price=None,
        nominal=None,
        coupon_rate=None,
    )
    assert dq.overall == "critical"
    assert not dq.is_rated
    assert any("MISSING_ID" in i for i in dq.issues)


def test_missing_currency_is_critical():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=10.0,
        currency="",
        maturity_date=None,
        status="active",
        issuer=None,
        price=None,
        nominal=None,
        coupon_rate=None,
    )
    assert dq.overall == "critical"
    assert not dq.is_rated


def test_ytm_extreme_is_critical():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=999.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=5.0,
    )
    assert dq.overall == "critical"
    assert any("YTM_TOO_HIGH" in i for i in dq.issues)


def test_ytm_negative_extreme_is_critical():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=-50.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=5.0,
    )
    assert dq.overall == "critical"


def test_ytm_high_but_not_extreme_is_warning():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=150.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=5.0,
    )
    assert dq.overall == "warning"
    assert dq.is_rated
    assert dq.confidence == "medium"


def test_stale_data_is_warning():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=10.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=5.0,
        fetched_at=datetime.now(UTC) - timedelta(hours=MAX_DATA_AGE_HOURS * 4),
        isin="US1234567890",
    )
    assert dq.overall == "warning"
    assert any("STALE_DATA" in i for i in dq.issues)


def test_coupon_negative_is_critical():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=10.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=-5.0,
    )
    assert dq.overall == "critical"


def test_coupon_high_is_warning():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=10.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=200.0,
    )
    assert dq.overall == "warning"
    assert any("COUPON_EXCESSIVE" in i for i in dq.issues)


def test_defaulted_status_is_critical():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=10.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="defaulted",
        issuer="Any Corp",
        price=50.0,
        nominal=100.0,
        coupon_rate=5.0,
    )
    assert dq.overall == "critical"


def test_nominal_zero_is_critical():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=10.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=0.0,
        coupon_rate=5.0,
    )
    assert dq.overall == "critical"


def test_price_nominal_ratio_warning():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=10.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=1.0,
        nominal=1000.0,
        coupon_rate=5.0,
    )
    assert dq.overall == "warning"
    assert any("PRICE_TOO_LOW" in i for i in dq.issues)


def test_score_bond_safe_returns_score_for_valid_data():
    dq, score = score_bond_safe(
        internal_id="OK-1",
        yield_to_maturity=12.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=8.0,
        fetched_at=datetime.now(UTC) - timedelta(hours=1),
    )
    assert dq.overall == "ok"
    assert score is not None
    assert score.score > 0


def test_score_bond_safe_returns_none_for_critical():
    dq, score = score_bond_safe(
        internal_id="BAD-1",
        yield_to_maturity=999.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=5.0,
    )
    assert dq.overall == "critical"
    assert score is None


def test_score_bond_safe_discounts_warnings():
    dq, score = score_bond_safe(
        internal_id="WARN-1",
        yield_to_maturity=120.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=5.0,
        fetched_at=datetime.now(UTC) - timedelta(hours=1),
    )
    assert dq.overall == "warning"
    assert score is not None
    from scoring.engine import score_bond as raw_score_bond

    raw = raw_score_bond(
        internal_id="WARN-1",
        yield_to_maturity=120.0,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=5.0,
    )
    assert score.score == round(raw.score * 0.85, 2)


def test_missing_ytm_is_warning():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=None,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="active",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=5.0,
    )
    assert dq.overall == "warning"
    assert any("YTM_MISSING" in i for i in dq.issues)


def test_empty_whitespace_id():
    dq = validate_bond_data(
        internal_id="   ",
        yield_to_maturity=10.0,
        currency="USD",
        maturity_date=None,
        status="active",
        issuer=None,
        price=None,
        nominal=None,
        coupon_rate=None,
    )
    assert dq.overall == "critical"


def test_multiple_warnings_do_not_escalate_to_critical():
    dq = validate_bond_data(
        internal_id="X",
        yield_to_maturity=None,
        currency="USD",
        maturity_date=date(2030, 1, 1),
        status="matured",
        issuer="Treasury",
        price=100.0,
        nominal=100.0,
        coupon_rate=5.0,
        fetched_at=datetime.now(UTC) - timedelta(hours=MAX_DATA_AGE_HOURS * 4),
    )
    assert dq.overall == "warning"
    assert len(dq.issues) >= 3
    assert dq.is_rated
