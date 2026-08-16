"""Comprehensive tests for scoring.eligibility (the portfolio Eligibility Gate)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from scoring.eligibility import (
    _robust_anomaly_z,
    check_eligibility,
    filter_eligible,
    peer_ytms_by_currency,
)


def _bond(internal_id="B", price=100.0, ytm=10.0, status="active", currency="BYN",
          maturity=date(2028, 1, 1), nominal=1000):
    return SimpleNamespace(
        internal_id=internal_id,
        price=price,
        nominal=nominal,
        yield_to_maturity=ytm,
        status=status,
        currency=currency,
        maturity_date=maturity,
    )


def test_check_eligibility_normal_bond_passes():
    res = check_eligibility(internal_id="B", price_pct=100.0, ytm_pct=10.0,
                            status="active", maturity_date=date(2028, 1, 1))
    assert res.eligible is True


def test_check_eligibility_excluded_status():
    for status in ("defaulted", "bankrupt", "suspended", "delisted", "matured"):
        res = check_eligibility(internal_id="B", price_pct=100, ytm_pct=10, status=status)
        assert res.eligible is False
        assert res.kind == "status"


def test_check_eligibility_expired_maturity():
    res = check_eligibility(internal_id="B", price_pct=100, ytm_pct=10,
                            status="active", maturity_date=date(2020, 1, 1))
    assert res.eligible is False
    assert res.kind == "expired"


def test_check_eligibility_no_market_data():
    res = check_eligibility(internal_id="B")
    assert res.eligible is False
    assert res.kind == "no_data"


def test_check_eligibility_negative_ytm_excluded():
    res = check_eligibility(internal_id="B", price_pct=100, ytm_pct=-5)
    assert res.eligible is False
    assert res.kind == "extreme_risk"


def test_check_eligibility_extreme_ytm_1545_excluded():
    res = check_eligibility(internal_id="B", price_pct=100, ytm_pct=1545)
    assert res.eligible is False
    assert res.kind == "extreme_risk"


def test_check_eligibility_distribution_price_low_with_high_ytm():
    res = check_eligibility(internal_id="B", price_pct=70, ytm_pct=40)
    assert res.eligible is False
    assert res.kind == "distribution"


def test_check_eligibility_distribution_not_triggered_when_price_ok():
    res = check_eligibility(internal_id="B", price_pct=95, ytm_pct=40)
    assert res.kind != "distribution"


def test_check_eligibility_extreme_low_price():
    res = check_eligibility(internal_id="B", price_pct=20, ytm_pct=10)
    assert res.eligible is False
    assert res.kind == "extreme_risk"


def test_check_eligibility_anomaly_detected_against_peers():
    peers = [4.0, 6.0, 8.0, 10.0, 12.0, 15.0]
    res = check_eligibility(internal_id="B", price_pct=100, ytm_pct=57.6,
                            status="active", peer_ytms=peers,
                            maturity_date=date(2028, 1, 1))
    assert res.eligible is False
    assert res.kind == "anomaly"


def test_check_eligibility_anomaly_skipped_with_few_peers():
    res = check_eligibility(internal_id="B", price_pct=100, ytm_pct=57.6,
                            status="active", peer_ytms=[4.0, 6.0, 8.0],
                            maturity_date=date(2028, 1, 1))
    assert res.eligible is True


def test_filter_eligible_splits_extreme_and_normal():
    bonds = [
        _bond(internal_id="good1", ytm=8),
        _bond(internal_id="good2", ytm=12),
        _bond(internal_id="crazy", ytm=1545),
        _bond(internal_id="expired", ytm=10, maturity=date(2020, 1, 1)),
    ]
    eligible, excluded = filter_eligible(bonds)
    ids = {b.internal_id for b in eligible}
    assert ids == {"good1", "good2"}
    assert set(excluded) == {"crazy", "expired"}


def test_filter_eligible_reports_reason_kinds():
    bonds = [_bond(internal_id="x", ytm=1545)]
    _, excluded = filter_eligible(bonds)
    assert excluded["x"].kind == "extreme_risk"


def test_peer_ytms_by_currency_groups_positive_ytm():
    bonds = [
        _bond(internal_id="a", currency="USD", ytm=5),
        _bond(internal_id="b", currency="USD", ytm=7),
        _bond(internal_id="c", currency="BYN", ytm=12),
        _bond(internal_id="d", currency="BYN", ytm=None),
    ]
    grouped = peer_ytms_by_currency(bonds)
    assert grouped["USD"] == [5.0, 7.0]
    assert grouped["BYN"] == [12.0]


def test_robust_anomaly_z_positive_for_high_outlier():
    z = _robust_anomaly_z(57.6, [4.0, 6.0, 8.0, 10.0, 12.0, 15.0])
    assert z is not None and z > 4.0


def test_robust_anomaly_z_negative_for_low_outlier():
    z = _robust_anomaly_z(2.0, [8.0, 10.0, 12.0, 14.0, 16.0])
    assert z is not None and z < 0


def test_robust_anomaly_z_none_when_too_few_peers():
    assert _robust_anomaly_z(2.0, [8.0, 10.0]) is None
