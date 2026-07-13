"""Human-readable explanation of a bond's Reward/Risk Score.

Turns the numeric :class:`ScoreBreakdown` into plain-language factors, a verdict
and a short summary — the "why should I buy this?" answer that makes the score
actionable for a non-professional investor. Pure functions, no I/O.
"""
from __future__ import annotations

from scoring.models import BondScore, ScoreBreakdown

__all__ = ["ExplainedScore", "ScoreFactor", "explain_score"]


class ScoreFactor:
    """One line of the explanation."""

    __slots__ = ("component", "detail", "impact", "label", "points")

    def __init__(self, component: str, label: str, points: float, detail: str) -> None:
        self.component = component
        self.label = label
        self.points = round(points, 2)
        self.impact = "positive" if points > 0 else "negative" if points < 0 else "neutral"
        self.detail = detail

    def as_dict(self) -> dict:
        return {
            "component": self.component,
            "label": self.label,
            "points": self.points,
            "impact": self.impact,
            "detail": self.detail,
        }


class ExplainedScore:
    """Full explanation payload."""

    __slots__ = ("factors", "score", "strengths", "summary", "tier", "verdict", "weaknesses")

    def __init__(
        self,
        *,
        score: float,
        tier: str,
        verdict: str,
        summary: str,
        factors: list[ScoreFactor],
        strengths: list[str],
        weaknesses: list[str],
    ) -> None:
        self.score = round(score, 2)
        self.tier = tier
        self.verdict = verdict
        self.summary = summary
        self.factors = factors
        self.strengths = strengths
        self.weaknesses = weaknesses

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "tier": self.tier,
            "verdict": self.verdict,
            "summary": self.summary,
            "factors": [f.as_dict() for f in self.factors],
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
        }


_VERDICTS: dict[str, tuple[str, str]] = {
    "S": ("Сильная возможность", "Одна из лучших облигаций по соотношению доходность/риск."),
    "A": ("Хорошая возможность", "Привлекательный профиль: доходность оправдывает риски."),
    "B": ("Умеренно интересна", "Разумный вариант, но есть заметные компромиссы."),
    "C": ("Средняя", "Ничем особо не выделяется — подходит скорее для диверсификации."),
    "D": ("Слабая / избегать", "Риски перевешивают доходность — лучше поискать альтернативу."),
}


def _yield_detail(ytm_pct: float | None) -> str:
    if ytm_pct is None or ytm_pct <= 0:
        return "Доходность к погашению не указана — оценить сложно."
    if ytm_pct >= 12:
        return f"Высокая доходность к погашению {ytm_pct:.1f}% годовых."
    if ytm_pct >= 7:
        return f"Умеренная доходность к погашению {ytm_pct:.1f}% годовых."
    return f"Невысокая доходность к погашению {ytm_pct:.1f}% годовых."


def _currency_detail(currency: str) -> str:
    cur = currency.upper()
    if cur == "USD":
        return "Валюта USD — защита от девальвации рубля."
    if cur in {"XAU", "XAG", "XPT"}:
        return f"Металл ({cur}) — защитный актив против инфляции."
    if cur == "BYN":
        return "Валюта BYN — есть валютный риск при девальвации."
    if cur == "EUR":
        return "Валюта EUR — нейтральный валютный профиль."
    return f"Валюта {cur}."


def _duration_detail(points: float) -> str:
    if points >= 20:
        return "Короткий срок до погашения — низкий процентный риск."
    if points >= 10:
        return "Средний срок до погашения — умеренный процентный риск."
    if points <= -10:
        return "Длинный срок до погашения — высокий процентный риск."
    return "Срок до погашения — сбалансированный."


def _liquidity_detail(points: float) -> str:
    if points >= 10:
        return "Хорошая ликвидность: активный статус и есть рыночная цена."
    if points <= 0:
        return "Ограниченная ликвидность — возможны сложности с выходом."
    return "Приемлемая ликвидность."


def _credit_detail(points: float) -> str:
    if points >= 10:
        return "Государственный эмитент — минимальный кредитный риск."
    if points <= -10:
        return "Повышенный кредитный риск эмитента."
    if points < 0:
        return "Корпоративный эмитент — умеренный кредитный риск."
    return "Кредитный риск эмитента в норме."


def _inflation_detail(points: float) -> str:
    if points > 0:
        return "Доходность покрывает инфляционные ожидания."
    if points < 0:
        return "Доходность может не покрывать инфляцию."
    return "Инфляционный профиль нейтральный."


def _metal_detail() -> str:
    return "Дополнительная премия за привязку к драгметаллу."


def explain_score(
    score: BondScore,
    *,
    currency: str,
    ytm_pct: float | None,
) -> ExplainedScore:
    """Build a plain-language explanation of a computed bond score."""
    b: ScoreBreakdown = score.breakdown
    factors: list[ScoreFactor] = []

    def add(component: str, label: str, pts: float, detail: str, *, skip_zero: bool = False) -> None:
        if skip_zero and pts == 0:
            return
        factors.append(ScoreFactor(component, label, pts, detail))

    add("yield", "Доходность", b.yield_component, _yield_detail(ytm_pct))
    add("currency", "Валюта", b.currency_component, _currency_detail(currency))
    add("duration", "Срок / дюрация", b.duration_component, _duration_detail(b.duration_component))
    add("liquidity", "Ликвидность", b.liquidity_component, _liquidity_detail(b.liquidity_component))
    add("credit", "Кредитный риск", b.credit_risk_component, _credit_detail(b.credit_risk_component))
    add("inflation", "Инфляция", b.inflation_component, _inflation_detail(b.inflation_component))
    add("metal", "Драгметалл", b.metal_component, _metal_detail(), skip_zero=True)

    factors.sort(key=lambda f: abs(f.points), reverse=True)
    strengths = [f.detail for f in factors if f.impact == "positive"][:3]
    weaknesses = [f.detail for f in factors if f.impact == "negative"][:3]

    verdict_title, verdict_text = _VERDICTS.get(score.tier, _VERDICTS["D"])
    lead = strengths[0] if strengths else (weaknesses[0] if weaknesses else "")
    summary = f"{verdict_text} {lead}".strip()

    return ExplainedScore(
        score=score.score,
        tier=score.tier,
        verdict=verdict_title,
        summary=summary,
        factors=factors,
        strengths=strengths,
        weaknesses=weaknesses,
    )
