"""Use-case layer for bond analytics (catalog, card, analysis, cashflow, history).

Routes in ``api/analytics/*`` stay thin: they parse HTTP input, call a service
method, and return a DTO. All ORM access and domain orchestration lives here
(or in the repositories the service delegates to).
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

from api.analytics._helpers import _all_bonds, _get_bond_or_404, _score_for_bond
from api.dto import analytics as dto
from desk import relative_value as desk_rv
from desk.cashflow import DEFAULT_DAY_COUNT
from desk.cashflow import accrued_interest as dc_accrued
from ml.repository import predictions_for_bond
from portfolio.income import bond_cashflows
from scraper.config import get_settings
from scraper.db import session_scope
from scraper.repositories import history as history_repo
from telegram_bot.subscriptions import STAR_PLANS


class BondService:
    """Bond analytics use cases shared by the API routers."""

    @staticmethod
    async def subscribe_info() -> dto.SubscribeInfo:
        username = (get_settings().telegram.bot_username or "").lstrip("@")
        deep_link = f"https://t.me/{username}?start=subscribe" if username else None
        yookassa_configured = bool(
            os.environ.get("YOOKASSA_SHOP_ID", "") and os.environ.get("YOOKASSA_SECRET_KEY", "")
        )
        yookassa_plans: list[dto.YookassaPlan] = []
        if yookassa_configured:
            yookassa_plans = [
                dto.YookassaPlan(
                    tier="pro",
                    name="Pro",
                    price=os.environ.get("YOOKASSA_PRO_PRICE", "29.00"),
                    currency=os.environ.get("YOOKASSA_CURRENCY", "BYN"),
                    interval="month",
                ),
                dto.YookassaPlan(
                    tier="enterprise",
                    name="Enterprise",
                    price=os.environ.get("YOOKASSA_ENTERPRISE_PRICE", "99.00"),
                    currency=os.environ.get("YOOKASSA_CURRENCY", "BYN"),
                    interval="month",
                ),
            ]
        return dto.SubscribeInfo(
            provider="telegram_stars",
            yookassa_configured=yookassa_configured,
            yookassa_plans=yookassa_plans,
            bot_username=username or None,
            deep_link=deep_link,
            plans=[
                dto.SubscribePlan(
                    tier=p.tier,
                    name=p.name,
                    stars=p.stars,
                    duration_days=p.duration_days,
                    blurb=p.blurb,
                )
                for p in STAR_PLANS.values()
            ],
        )

    @staticmethod
    async def top(limit: int, offset: int) -> list[dto.TopBondRow]:
        from scoring.repository import top_scores

        async with session_scope() as session:
            rows = await top_scores(session, limit=limit, offset=offset)
        return [
            dto.TopBondRow(internal_id=s.internal_id, score=float(s.score), tier=s.tier)
            for s in rows
        ]

    @staticmethod
    async def by_currency(currency: str) -> list[dto.CurrencyBondRow]:
        bonds = await _all_bonds()
        out = [b for b in bonds if str(b.currency).upper() == currency.upper()]
        rows: list[dto.CurrencyBondRow] = []
        for b in out:
            rows.append(
                dto.CurrencyBondRow(
                    internal_id=b.internal_id,
                    name=b.name,
                    currency=b.currency,
                    yield_to_maturity=float(b.yield_to_maturity)
                    if b.yield_to_maturity is not None
                    else None,
                    price=float(b.price) if b.price is not None else None,
                    issuer=b.issuer,
                    maturity_date=b.maturity_date.isoformat() if b.maturity_date else None,
                    status=b.status,
                )
            )
        return rows

    @staticmethod
    async def card(internal_id: str, tier: str) -> dto.BondCard:
        """Карточка облигации: факты + Score + вердикт.

        Free-пользователь видит факты, число Score и тир, но полный разбор
        («почему») скрыт. Pro получает объяснение сразу внутри карточки —
        это и есть точка апселла.
        """
        bond = await _get_bond_or_404(internal_id)
        score = await _score_for_bond(bond)
        # Paid tiers include B2B tiers (affiliate/api_pro/whitelabel), which
        # FEATURE_FLAGS grants access_bond_analysis but the old check excluded.
        is_pro = tier in {"pro", "enterprise", "api_pro", "whitelabel", "affiliate"}
        if is_pro:
            ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity else None
            analysis = _explain(bond, score, ytm)
            return dto.BondCard(
                bond=dto.bond_facts(bond),
                score=round(float(score.score), 2),
                tier=score.tier,
                analysis=analysis,
                analysis_locked=False,
            )
        return dto.BondCard(
            bond=dto.bond_facts(bond),
            score=round(float(score.score), 2),
            tier=score.tier,
            analysis=None,
            analysis_locked=True,
            upgrade_hint="Полный разбор и вердикт доступны в подписке Pro.",
        )

    @staticmethod
    async def analysis(internal_id: str) -> dto.BondAnalysisPayload:
        """Полный разбор одной облигации: объяснение Score, ML-прогноз, RV-сигнал.

        Единый ответ на вопрос «покупать или нет и почему» — ключевая ценность Pro.
        """
        from scoring.disclaimer import DISCLAIMER_FULL

        bond = await _get_bond_or_404(internal_id)
        score = await _score_for_bond(bond)
        ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity else None

        all_bonds = await _all_bonds()
        rv_signal = None
        for s in desk_rv.relative_value_signals(all_bonds):
            if s.internal_id == internal_id:
                rv_signal = dto.RvSignal(
                    internal_id=s.internal_id,
                    side=s.side,
                    z_score=round(float(s.z_score), 3) if s.z_score is not None else None,
                    spread_pct=round(float(s.spread_pct), 3) if s.spread_pct is not None else None,
                )
                break

        ml_prediction = None
        async with session_scope() as session:
            rows = await predictions_for_bond(session, internal_id, limit=1)
        if rows:
            p = rows[0]
            ml_prediction = dto.MlPrediction(
                decision=p.decision,
                confidence=round(float(p.confidence), 3),
                predicted_ytm=float(p.predicted_ytm) if p.predicted_ytm is not None else None,
                predicted_return_pct=float(p.predicted_return_pct)
                if p.predicted_return_pct is not None
                else None,
                explanation=p.explanation or [],
            )

        return dto.BondAnalysisPayload(
            bond=dto.bond_facts(bond),
            analysis=_explain(bond, score, ytm),
            relative_value=rv_signal,
            ml_prediction=ml_prediction,
            disclaimer=DISCLAIMER_FULL,
        )

    @staticmethod
    async def cashflow(internal_id: str, amount: float) -> dto.CashflowPlan:
        """График купонных выплат при вложении ``amount`` в облигацию.

        «Сколько денег и когда я получу» — суть fixed income. Возвращает даты и
        суммы купонов + возврат номинала при погашении, годовой доход и доходность
        на вложенные средства (yield-on-cost).
        """
        bond = await _get_bond_or_404(internal_id)
        settlement = date.today()
        flows = bond_cashflows(
            internal_id=internal_id,
            amount_invested=Decimal(str(amount)),
            coupon_rate=bond.coupon_rate,
            coupon_frequency=bond.coupon_frequency,
            maturity_date=bond.maturity_date,
            price=bond.price,
            issue_date=bond.start_date,
            settlement=settlement,
        )
        total_coupons = sum((f.amount for f in flows if f.kind == "coupon"), start=Decimal("0"))
        ann = Decimal("0")
        face = (
            Decimal(str(amount)) * Decimal("100") / bond.price
            if bond.price
            else Decimal(str(amount))
        )
        if bond.coupon_rate and bond.coupon_rate > 0:
            ann = (face * bond.coupon_rate / Decimal("100")).quantize(Decimal("0.01"))
        accrued = 0.0
        if (
            bond.coupon_rate
            and bond.coupon_rate > 0
            and bond.start_date is not None
            and bond.maturity_date is not None
        ):
            accrued_per_face = dc_accrued(
                coupon_rate_pct=float(bond.coupon_rate),
                coupon_frequency=bond.coupon_frequency or 2,
                issue_date=bond.start_date,
                maturity_date=bond.maturity_date,
                asof=settlement,
                convention=DEFAULT_DAY_COUNT,
                face=100.0,
            )
            accrued = float(accrued_per_face) * float(face) / 100.0
        return dto.CashflowPlan(
            bond=dto.bond_facts(bond),
            amount_invested=round(amount, 2),
            annual_income=float(ann),
            yield_on_cost=round(float(ann / Decimal(str(amount)) * 100), 2) if amount > 0 else 0.0,
            total_coupons=float(total_coupons),
            accrued_interest=round(accrued, 2),
            cashflows=[f.as_dict() for f in flows],
        )

    @staticmethod
    async def history(internal_id: str, months: int) -> list[dto.HistoryPoint]:
        """История цены и YTM для графика."""
        cutoff = date.today() - timedelta(days=months * 30)
        async with session_scope() as session:
            rows = await history_repo.bond_history_since(session, internal_id, cutoff)
        return [
            dto.HistoryPoint(
                date=r.date.isoformat(),
                price=float(r.price) if r.price is not None else None,
                ytm=float(r.yield_) if r.yield_ is not None else None,
            )
            for r in rows
        ]


def _explain(bond, score, ytm: float | None) -> dict:
    from scoring.explain import explain_score

    return explain_score(score, currency=bond.currency, ytm_pct=ytm).as_dict()
