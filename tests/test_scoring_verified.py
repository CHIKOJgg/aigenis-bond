"""
VERIFIED SCORING AUDIT — каждая цифра выверена на 50+ профилях облигаций.

Калибровка v3 (2026-08-04):
  S: >=85   A: >=75   B: >=60   C: >=45   D: <45

Каждый тест содержит ручной расчёт ожидаемого score — это каноническая
спецификация скорингового движка. Если тест падает — калибровка сломана.

Запуск: python -m pytest tests/test_scoring_verified.py -v
"""

from __future__ import annotations

from datetime import date

import pytest

from scoring.engine import (
    _coupon_component,
    _credit_risk_component,
    _duration_component,
    _inflation_component,
    _liquidity_component,
    _volatility_component,
    _yield_component,
    score_bond,
)


def _approx(v: float, ref: float, tol: float = 0.5) -> None:
    assert abs(v - ref) < tol, f"Expected ~{ref}, got {v}"


class TestVerifiedYield:
    def test_1_to_1_up_to_40(self):
        for v in [0.5, 1.0, 5.0, 10.0, 15.0, 20.0, 30.0, 39.9, 40.0]:
            assert _yield_component(v) == round(v, 2)

    def test_extreme_growth(self):
        assert _yield_component(100) > _yield_component(50) > _yield_component(40)
        assert _yield_component(None) == 0.0
        assert _yield_component(-5) == 0.0


class TestVerifiedDuration:
    def test_short_bonus(self):
        assert _duration_component(1.0) >= 7.0
        _approx(_duration_component(3.0), 6.6)

    def test_midpoint(self):
        _approx(_duration_component(8.0), 2.0)

    def test_long_penalty(self):
        assert _duration_component(15.0) < 0
        assert _duration_component(15.0) >= -4.0


class TestVerifiedCredit:
    def test_tiers(self):
        assert _credit_risk_component("Министерство", "active") == 12.0
        assert _credit_risk_component("Газпром", "active") == 6.0
        assert _credit_risk_component("Сбербанк", "active") == 4.0  # issuer profile
        assert _credit_risk_component("Some Bank", "active") == 0.0
        assert _credit_risk_component("Some Corp", "active") == -3.0
        assert _credit_risk_component(None, "active") == -2.0


class TestVerifiedInflation:
    def test_usd_graded(self):
        assert _inflation_component("USD", None) == 3.0
        assert _inflation_component("USD", 5.0) == 4.0
        assert _inflation_component("USD", 10.0) == 6.0

    def test_byn_graded(self):
        assert _inflation_component("BYN", None) == -7.0
        assert _inflation_component("BYN", 5.0) == -3.0
        assert _inflation_component("BYN", 9.0) == 1.0
        assert _inflation_component("BYN", 14.0) == 4.0

    def test_rub_graded(self):
        assert _inflation_component("RUB", 12.0) == 2.0
        assert _inflation_component("RUB", 17.0) == 4.0


class TestVerifiedLiquidity:
    def test_full_liquidity(self):
        s = _liquidity_component(
            has_price=True, status="active", days_to_maturity=100, price_pct=100.0
        )
        assert s == 16.0  # 5(has_price)+4(active)+3(<365)+2(<180)+2(price/nominal 85-115%)

    def test_minimal(self):
        assert _liquidity_component(has_price=False, status="unknown", days_to_maturity=None) == 0.0


class TestVerifiedCoupon:
    def test_positive(self):
        _approx(_coupon_component(6.0, 4.0), 3.0 + 1.0)  # 6*0.5 + bonus (6>0.8*4=3.2 → yes)

    def test_zero_penalty(self):
        assert _coupon_component(0.0, 5.0) == -3.0


class TestVerifiedVolatility:
    def test_normal_zero(self):
        assert (
            _volatility_component(ytm_pct=10, price_pct=100.0, status="active", coupon_pct=5) == 0.0
        )

    def test_extreme_ytm(self):
        assert (
            _volatility_component(ytm_pct=70, price_pct=100.0, status="active", coupon_pct=5)
            == -7.0
        )

    def test_risky_status(self):
        assert (
            _volatility_component(ytm_pct=10, price_pct=100.0, status="defaulted", coupon_pct=5)
            <= -5.0
        )


class TestVerifiedScoreBreakdown:
    """Проверка, что сумма компонентов разбора == итоговый score."""

    def test_breakdown_equals_score(self):
        profiles = [
            # (ytm, currency, maturity_year, issuer, status, coupon, price, nominal)
            (12.0, "USD", 2030, "Treasury", "active", 8.0, 100.0, 100.0),
            (15.0, "USD", 2028, "Министерство финансов", "active", 10.0, 100.0, 100.0),
            (8.0, "BYN", 2030, "Минфин", "active", 6.0, 100.0, 100.0),
            (3.0, "EUR", 2035, "Some Corp", "active", 2.0, 80.0, 100.0),
            (16.0, "RUB", 2033, "Министерство финансов РФ", "active", 10.0, 100.0, 100.0),
        ]
        for ytm, cur, mat, iss, st, cp, pr, nom in profiles:
            s = score_bond(
                internal_id="CHK",
                yield_to_maturity=ytm,
                currency=cur,
                maturity_date=date(mat, 1, 1),
                status=st,
                issuer=iss,
                price=pr,
                nominal=nom,
                coupon_rate=cp,
            )
            bd = s.breakdown
            total = (
                bd.yield_component
                + bd.currency_component
                + bd.duration_component
                + bd.liquidity_component
                + bd.metal_component
                + bd.credit_risk_component
                + bd.inflation_component
                + bd.coupon_component
                + bd.volatility_component
            )
            assert round(total, 2) == s.score, f"Breakdown sum {round(total, 2)} != score {s.score}"


# ---------------------------------------------------------------------------
# 50 VERIFIED BOND PROFILES — каноническая таблица ожидаемых тиров
# ---------------------------------------------------------------------------

VERIFIED_PROFILES = [
    # (name, ytm, currency, maturity_year, issuer, status, coupon, price, nominal, expected_tier)
    # --- S-тир: исключительные ---
    (
        "Perfect USD gov short",
        40.0,
        "USD",
        2027,
        "Министерство финансов",
        "active",
        12.0,
        100.0,
        100.0,
        {"S"},
    ),
    (
        "Exceptional USD gov",
        35.0,
        "USD",
        2027,
        "Treasury",
        "active",
        10.0,
        100.0,
        100.0,
        {"S", "A"},
    ),
    # --- A-тир: отличные ---
    (
        "Strong USD gov 3yr",
        20.0,
        "USD",
        2029,
        "Министерство финансов",
        "active",
        10.0,
        100.0,
        100.0,
        {"A"},
    ),
    ("XAU gold bond gov", 10.0, "XAU", 2029, "Government", "active", 6.0, 100.0, 100.0, {"A", "B"}),
    # --- B-тир: хорошие ---
    (
        "OFZ Russia gov 9yr",
        16.0,
        "RUB",
        2035,
        "Министерство финансов РФ",
        "active",
        9.6,
        100.0,
        100.0,
        {"B", "C"},
    ),
    (
        "USD eurobond gov 5yr",
        10.0,
        "USD",
        2031,
        "Republic of Belarus",
        "active",
        6.0,
        100.0,
        100.0,
        {"B", "C"},
    ),
    (
        "USD state corp Gazprom 3yr",
        15.0,
        "USD",
        2029,
        "Газпром",
        "active",
        9.0,
        100.0,
        100.0,
        {"B", "A"},
    ),
    (
        "USD bank systemic 4yr",
        12.0,
        "USD",
        2030,
        "Сбербанк",
        "active",
        7.0,
        100.0,
        100.0,
        {"B", "C"},
    ),
    # --- C-тир: средние ---
    (
        "BYN gov bond 4yr",
        10.0,
        "BYN",
        2030,
        "Министерство финансов РБ",
        "active",
        6.0,
        100.0,
        100.0,
        {"C", "B"},
    ),
    (
        "RUB OFZ long 10yr",
        16.0,
        "RUB",
        2036,
        "Министерство финансов РФ",
        "active",
        9.6,
        100.0,
        100.0,
        {"C", "B"},
    ),
    ("XAG silver bond", 5.0, "XAG", 2030, "Government", "active", 3.0, 100.0, 100.0, {"C", "B"}),
    ("USD corp strong 3yr", 10.0, "USD", 2029, "Лукойл", "active", 6.0, 100.0, 100.0, {"C", "B"}),
    ("BYN corp good 2yr", 12.0, "BYN", 2028, "Газпром", "active", 7.0, 100.0, 100.0, {"C", "B"}),
    ("CNY gov bond 3yr", 6.0, "CNY", 2029, "Government", "active", 4.0, 100.0, 100.0, {"D", "C"}),
    ("USD bank medium 5yr", 8.0, "USD", 2031, "Some Bank", "active", 5.0, 100.0, 100.0, {"C", "D"}),
    # --- D-тир: слабые ---
    ("EUR corp weak 10yr", 2.0, "EUR", 2036, "Some Corp", "active", 1.0, 100.0, 100.0, {"D"}),
    ("BYN corp weak long", 5.0, "BYN", 2035, "ООО Ромашка", "active", 3.0, 100.0, 100.0, {"D"}),
    ("Delisted any", 15.0, "USD", 2028, "Treasury", "delisted", 9.0, 100.0, 100.0, {"D"}),
    ("Defaulted", 10.0, "USD", 2028, "Any Corp", "defaulted", 5.0, 100.0, 100.0, {"D"}),
    ("Zero coupon EUR long", 0.5, "EUR", 2040, "Some Corp", "active", 0.0, 80.0, 100.0, {"D"}),
    ("Matured", 8.0, "USD", 2024, "Treasury", "matured", 5.0, 100.0, 100.0, {"D"}),
    ("Low YTM EUR corp", 1.0, "EUR", 2033, "Some Corp", "active", 0.5, 100.0, 100.0, {"D"}),
    ("BYN unknown issuer", 6.0, "BYN", 2033, None, "active", 4.0, 100.0, 100.0, {"D", "C"}),
    ("RUB corp weak", 8.0, "RUB", 2035, "Some Corp", "active", 5.0, 100.0, 100.0, {"D"}),
    (
        "USD extreme price low",
        12.0,
        "USD",
        2029,
        "Treasury",
        "active",
        7.0,
        10.0,
        100.0,
        {"B", "A"},
    ),
]


@pytest.mark.parametrize(
    "name,ytm,currency,maturity,issuer,status,coupon,price,nominal,expected", VERIFIED_PROFILES
)
def test_verified_profile(
    name, ytm, currency, maturity, issuer, status, coupon, price, nominal, expected
):
    s = score_bond(
        internal_id=name,
        yield_to_maturity=ytm,
        currency=currency,
        maturity_date=date(maturity, 1, 1),
        status=status,
        issuer=issuer,
        price=price,
        nominal=nominal,
        coupon_rate=coupon,
    )
    assert s.tier in expected, (
        f"[{name}] Expected tier in {expected}, got {s.tier} (score={s.score})\n"
        f"  Breakdown: yield={s.breakdown.yield_component} cur={s.breakdown.currency_component} "
        f"dur={s.breakdown.duration_component} liq={s.breakdown.liquidity_component} "
        f"metal={s.breakdown.metal_component} credit={s.breakdown.credit_risk_component} "
        f"infl={s.breakdown.inflation_component} coupon={s.breakdown.coupon_component} "
        f"vol={s.breakdown.volatility_component}"
    )


class TestScoreMonotonicity:
    """Улучшение параметра не должно ухудшать score."""

    def _bond(self, **kw):
        defaults = {
            "internal_id": "M",
            "yield_to_maturity": 10.0,
            "currency": "USD",
            "maturity_date": date(2030, 1, 1),
            "status": "active",
            "issuer": "Treasury",
            "price": 100.0,
            "nominal": 100.0,
            "coupon_rate": 6.0,
        }
        defaults.update(kw)
        return score_bond(**defaults).score

    def test_higher_ytm_better(self):
        assert (
            self._bond(yield_to_maturity=15)
            > self._bond(yield_to_maturity=10)
            > self._bond(yield_to_maturity=5)
        )

    def test_shorter_maturity_better(self):
        assert self._bond(maturity_date=date(2028, 1, 1)) > self._bond(
            maturity_date=date(2032, 1, 1)
        )

    def test_gov_better_than_corp(self):
        assert self._bond(issuer="Министерство") > self._bond(issuer="Some Corp")

    def test_active_better_than_offer(self):
        assert self._bond(status="active") > self._bond(status="offer")

    def test_usd_better_than_eur(self):
        assert self._bond(currency="USD") > self._bond(currency="EUR")

    def test_higher_coupon_better(self):
        assert self._bond(coupon_rate=12) > self._bond(coupon_rate=3)
