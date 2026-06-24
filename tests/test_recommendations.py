"""Тесты recommendations + auto-rebalance."""

from __future__ import annotations

from datetime import UTC, date
from decimal import Decimal

from ml.engine import train_buy_classifier, train_ytm_regressor
from ml.features import build_dataset
from portfolio.rebalance import DEFAULT_DRIFT_THRESHOLD, build_plan
from recommendations.engine import recommend_bonds
from scoring.models import UserPreferences
from scraper.models import Bond


def _bond(iid: str, ytm: float, cur: str, maturity: date, status: str = "active") -> Bond:
    from datetime import datetime

    return Bond(
        internal_id=iid,
        name=iid,
        currency=cur,  # type: ignore[arg-type]
        yield_to_maturity=Decimal(str(ytm)),
        maturity_date=maturity,
        status=status,  # type: ignore[arg-type]
        issuer="Министерство финансов",
        price=Decimal("99"),
        fetched_at=datetime.now(UTC),
    )


def _train_models():
    today = date(2026, 6, 18)
    bonds = [_bond(f"B{i:03d}", 3 + i * 0.3, "USD", date(2028 + i, 1, 1)) for i in range(60)]
    history = {b.internal_id: [] for b in bonds}
    features = build_dataset(
        [
            {
                "internal_id": b.internal_id,
                "name": b.name,
                "currency": b.currency,
                "yield_to_maturity": b.yield_to_maturity,
                "coupon_rate": b.coupon_rate,
                "maturity_date": b.maturity_date,
                "price": b.price,
                "status": b.status,
                "issuer": b.issuer,
            }
            for b in bonds
        ],
        history,
        asof=today,
    )
    mv_reg, _ = train_ytm_regressor(features)
    mv_clf, _ = train_buy_classifier(features)
    return mv_reg.artifact_path, mv_clf.artifact_path, bonds


def test_recommend_bonds_returns_topk() -> None:
    reg_path, clf_path, bonds = _train_models()
    today = date(2026, 6, 18)
    prefs = UserPreferences(user_id=1, strategy="Balanced", share_usd=1.0, share_byn=0.0, share_metals=0.0)
    bond_dicts = [
        {
            "internal_id": b.internal_id,
            "name": b.name,
            "currency": b.currency,
            "yield_to_maturity": b.yield_to_maturity,
            "coupon_rate": b.coupon_rate,
            "maturity_date": b.maturity_date,
            "price": b.price,
            "status": b.status,
            "issuer": b.issuer,
        }
        for b in bonds
    ]
    recs = recommend_bonds(
        bond_dicts,
        prefs,
        history_by_bond={b.internal_id: [] for b in bonds},
        asof=today,
        top_k=5,
    )
    assert len(recs) <= 5
    assert all(r.decision in {"buy", "hold", "wait", "avoid"} for r in recs)
    assert recs[0].rank == 1


def test_build_plan_below_threshold() -> None:
    _, _, bonds = _train_models()
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Balanced")
    plan = build_plan(
        bonds=bonds,
        prefs=prefs,
        current_positions=[],
        current_total=Decimal("0"),
    )
    assert plan is None or plan.max_drift_observed >= DEFAULT_DRIFT_THRESHOLD


def test_build_plan_above_threshold() -> None:
    _, _, bonds = _train_models()
    prefs = UserPreferences(user_id=1, initial_capital=Decimal("10000"), strategy="Balanced")
    fake_positions = [
        type("Pos", (), {"internal_id": bonds[0].internal_id, "amount": Decimal("10000")})()
    ]
    plan = build_plan(
        bonds=bonds,
        prefs=prefs,
        current_positions=fake_positions,
        current_total=Decimal("10000"),
        drift_threshold=0.01,
    )
    assert plan is not None
    assert plan.max_drift_observed > 0.01
    assert plan.actions
