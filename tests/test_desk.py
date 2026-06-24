"""Тесты V4 desk: duration, yield_curve, RV, carry, repo, stress."""

from __future__ import annotations

from datetime import UTC, date
from decimal import Decimal

from desk import carry, duration, relative_value, repo, stress, yield_curve
from desk.models import StressScenario
from scraper.models import Bond


def _bond(
    iid: str,
    ytm: float,
    cur: str = "USD",
    maturity: date | None = None,
    coupon: float = 5.0,
    freq: int = 2,
    issuer: str = "Министерство финансов",
    price: float = 100.0,
    nominal: float = 1000.0,
) -> Bond:
    from datetime import datetime

    return Bond(
        internal_id=iid,
        name=iid,
        currency=cur,  # type: ignore[arg-type]
        yield_to_maturity=Decimal(str(ytm)),
        coupon_rate=Decimal(str(coupon)),
        coupon_frequency=freq,
        maturity_date=maturity,
        price=Decimal(str(price)),
        nominal=Decimal(str(nominal)),
        issuer=issuer,
        status="active",
        fetched_at=datetime.now(UTC),
    )


def test_duration_basic() -> None:
    bond = _bond("A", 6.0, maturity=date(2029, 1, 1), coupon=6.0, freq=2)
    rep = duration.duration_report(bond)
    assert rep.modified_duration > 0
    assert rep.macaulay_duration >= rep.modified_duration
    assert rep.dv01 != 0


def test_duration_key_rate() -> None:
    bond = _bond("A", 6.0, maturity=date(2030, 1, 1), coupon=5.0, freq=2)
    rep = duration.duration_report(bond)
    assert rep.key_rate_durations
    assert sum(rep.key_rate_durations.values()) > 0


def test_portfolio_duration_weighted() -> None:
    a = _bond("A", 5.0, maturity=date(2028, 1, 1))
    b = _bond("B", 7.0, maturity=date(2032, 1, 1))
    rep = duration.portfolio_duration([a, b], weights={"A": 0.7, "B": 0.3})
    assert rep.modified_duration > 0


def test_yield_curve_nelson_siegel() -> None:
    points = [
        yield_curve.CurvePoint(tenor="1Y", years=1.0, rate_pct=4.5),
        yield_curve.CurvePoint(tenor="5Y", years=5.0, rate_pct=5.5),
        yield_curve.CurvePoint(tenor="10Y", years=10.0, rate_pct=6.0),
        yield_curve.CurvePoint(tenor="30Y", years=30.0, rate_pct=6.3),
    ]
    params = yield_curve.fit_nelson_siegel(points)
    rate_3y = yield_curve.interpolate(
        yield_curve.YieldCurve(currency="USD", observed_at=__import__("datetime").datetime.now(), points=points),
        params,
        "3Y",
    )
    assert 3.0 < rate_3y < 8.0


def test_yield_curve_from_bonds() -> None:
    today = date.today()
    bonds = [
        _bond("A", 5.0, maturity=date(today.year + 1, 1, 1)),
        _bond("B", 6.0, maturity=date(today.year + 5, 1, 1)),
        _bond("C", 6.5, maturity=date(today.year + 10, 1, 1)),
    ]
    curve = yield_curve.curve_from_bonds(bonds)
    assert len(curve.points) >= 2
    assert curve.slope() > 0


def test_relative_value_basic() -> None:
    today = date.today()
    bonds = [
        _bond("A", 4.0, maturity=date(today.year + 2, 1, 1)),
        _bond("B", 5.0, maturity=date(today.year + 2, 1, 1)),
        _bond("C", 6.0, maturity=date(today.year + 2, 1, 1)),
        _bond("D", 9.0, maturity=date(today.year + 2, 1, 1)),
    ]
    signals = relative_value.relative_value_signals(bonds)
    sides = {s.side for s in signals}
    assert "buy" in sides or "sell" in sides


def test_carry_basic() -> None:
    bond = _bond("A", 5.0, coupon=8.0, maturity=date(2030, 1, 1))
    ct = carry.carry_for_bond(bond, funding_rate_pct=4.0, horizon_days=90)
    assert ct is not None
    assert ct.expected_pnl_pct > 0


def test_carry_ranking() -> None:
    bonds = [
        _bond("LOW", 4.0, coupon=4.0, maturity=date(2030, 1, 1)),
        _bond("HIGH", 6.0, coupon=10.0, maturity=date(2030, 1, 1)),
    ]
    ranked = carry.rank_carry(bonds, funding_rate_pct=5.0)
    assert ranked[0].expected_pnl_pct >= ranked[-1].expected_pnl_pct


def test_repo_deal_basic() -> None:
    bond = _bond("A", 5.0, issuer="Министерство финансов")
    deal = repo.repo_deal(bond, notional=Decimal("1000"), haircut_pct=1.0, repo_rate_pct=5.0, tenor_days=30)
    assert deal.cash_lent == Decimal("990.00")
    assert deal.accrued_interest > 0


def test_repo_haircut_by_issuer() -> None:
    assert repo.haircut_by_issuer("Министерство финансов") == 1.0
    assert repo.haircut_by_issuer("SomeBank") == 3.0
    assert repo.haircut_by_issuer("Unknown Corp") == 5.0


def test_stress_parallel() -> None:
    bonds = [_bond("A", 5.0, maturity=date(2030, 1, 1))]
    amounts = [(b, Decimal("10000")) for b in bonds]
    scn = StressScenario(
        kind="parallel",
        name="+100bp",
        description="Parallel +100bp",
        rate_shocks={"5Y": 1.0, "10Y": 1.0, "30Y": 1.0},
    )
    res = stress.run_stress(scn, amounts)
    assert res.pnl < 0


def test_stress_credit_shock() -> None:
    bonds = [_bond("A", 5.0, maturity=date(2030, 1, 1))]
    amounts = [(b, Decimal("10000")) for b in bonds]
    scn = StressScenario(
        kind="credit_shock",
        name="credit+150bp",
        description="",
        credit_spread_shock_bps=150.0,
    )
    res = stress.run_stress(scn, amounts)
    assert res.pnl < 0


def test_presets_present() -> None:
    assert "parallel_+100bp" in stress.PRESET_SCENARIOS
    assert "steepener_+50_+150" in stress.PRESET_SCENARIOS
    assert "inversion_+200_-50" in stress.PRESET_SCENARIOS
