"""Comprehensive tests for desk.repo (reverse-repo financing model)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from desk.repo import haircut_by_issuer, repo_deal


def _bond(internal_id="B", price=100.0):
    return SimpleNamespace(internal_id=internal_id, price=price)


def test_repo_deal_cash_lent_after_haircut():
    deal = repo_deal(_bond("B"), notional=Decimal("1000"), haircut_pct=5.0,
                     repo_rate_pct=10.0, tenor_days=365, asof=date(2024, 1, 1))
    assert deal.cash_lent == Decimal("950.00")
    assert deal.collateral_value == Decimal("1000.00")


def test_repo_deal_accrued_interest():
    deal = repo_deal(_bond("B"), notional=Decimal("1000"), haircut_pct=0.0,
                     repo_rate_pct=10.0, tenor_days=365, asof=date(2024, 1, 1))
    # collateral 1000 * 10% * 365/365 = 100
    assert deal.accrued_interest == Decimal("100.00")


def test_repo_deal_accrued_scales_with_tenor():
    deal = repo_deal(_bond("B"), notional=Decimal("1000"), haircut_pct=0.0,
                     repo_rate_pct=10.0, tenor_days=182, asof=date(2024, 1, 1))
    assert deal.accrued_interest == Decimal("49.86")


def test_repo_deal_bad_haircut_clamped_to_zero():
    deal = repo_deal(_bond("B"), notional=Decimal("1000"), haircut_pct=150.0,
                     repo_rate_pct=10.0, tenor_days=365, asof=date(2024, 1, 1))
    assert deal.haircut_pct == 0.0
    assert deal.cash_lent == Decimal("1000.00")


def test_haircut_by_issuer_government():
    assert haircut_by_issuer("Министерство финансов") == 1.0
    assert haircut_by_issuer("US Treasury") == 1.0
    assert haircut_by_issuer("Government of BYN") == 1.0


def test_haircut_by_issuer_bank():
    assert haircut_by_issuer("Беларусбанк") == 3.0
    assert haircut_by_issuer("Alpha Bank") == 3.0


def test_haircut_by_issuer_corporate():
    assert haircut_by_issuer("ООО Рога") == 5.0
    assert haircut_by_issuer(None) == 5.0
