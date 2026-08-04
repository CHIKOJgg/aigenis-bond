"""NLP chat endpoint — AI assistant for bond questions.

Gated behind `access_nlp_chat` (Pro/Enterprise). Answers user questions
about bonds using real market data as context.

Provider chain (first configured wins):
1. OpenRouter  — ``OPENROUTER_API_KEY`` (+ ``OPENROUTER_MODEL``)
2. OpenAI      — ``OPENAI_API_KEY`` (legacy fallback)
3. Local mode  — rule-based answers built from the database, so the chat
   keeps working even without any external LLM key (e.g. on a demo box).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select

from api.access_control import RequireFeature
from api.llm import llm_completion
from scoring.engine import score_bond
from scoring.explain import explain_score
from scoring.repository import get_score, score_from_orm
from scraper.db import session_scope
from scraper.orm import BondHistoryORM, BondORM, BondScoreORM

router = APIRouter(prefix="/api/v1", tags=["nlp"])


class ChatRequest(BaseModel):
    message: str
    context: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[str] = []


# --------------------------------------------------------------------------- #
# Bond context builders
# --------------------------------------------------------------------------- #


async def _build_bond_context(internal_id: str) -> str:
    """Load bond data and build context string for the LLM."""
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == internal_id))
        ).scalar_one_or_none()
        if bond is None:
            return f"Облигация {internal_id} не найдена в базе данных."

        score = (
            await session.execute(
                select(BondScoreORM).where(BondScoreORM.internal_id == internal_id)
            )
        ).scalar_one_or_none()

        cutoff = date.today() - timedelta(days=30)
        history = (
            (
                await session.execute(
                    select(BondHistoryORM)
                    .where(BondHistoryORM.internal_id == internal_id)
                    .where(BondHistoryORM.date >= cutoff)
                    .order_by(BondHistoryORM.date.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )
    lines = [
        f"Облигация: {bond.name} (ID: {bond.internal_id})",
        f"Валюта: {bond.currency}",
        f"Эмитент: {bond.issuer or 'Н/Д'}",
        f"Цена: {float(bond.price) if bond.price else 'Н/Д'}",
        f"Доходность к погашению: {float(bond.yield_to_maturity) if bond.yield_to_maturity else 'Н/Д'}%",
        f"Купон: {float(bond.coupon_rate) if bond.coupon_rate else 'Н/Д'}%",
        f"Частота купона: {bond.coupon_frequency or 'Н/Д'} раз/год",
        f"Погашение: {bond.maturity_date.isoformat() if bond.maturity_date else 'Н/Д'}",
        f"Статус: {bond.status}",
    ]
    if score:
        lines.append(f"Score Aigenis: {float(score.score)} (тир {score.tier})")
    if history:
        lines.append(
            f"Цена 30 дней назад: {float(history[-1].price) if history[-1].price else 'Н/Д'}"
        )
        lines.append(f"Цена сейчас: {float(history[0].price) if history[0].price else 'Н/Д'}")

    return "\n".join(lines)


async def _build_bond_context_entries(internal_id: str) -> tuple[str, str] | None:
    """Async helper: returns (bond_id, context_text) or None if bond not found."""
    ctx = await _build_bond_context(internal_id)
    if ctx.startswith("Облигация") and ctx.endswith("не найдена в базе данных."):
        return None
    return internal_id, ctx


async def _build_market_context() -> str:
    """Compact market snapshot so the LLM can answer with real data."""
    async with session_scope() as session:
        total = (await session.execute(select(func.count()).select_from(BondORM))).scalar_one()
        by_cur = (
            await session.execute(select(BondORM.currency, func.count()).group_by(BondORM.currency))
        ).all()
        top_scores = (
            (
                await session.execute(
                    select(BondScoreORM).order_by(BondScoreORM.score.desc()).limit(10)
                )
            )
            .scalars()
            .all()
        )
        ids = [s.internal_id for s in top_scores]
        bonds = (
            (await session.execute(select(BondORM).where(BondORM.internal_id.in_(ids))))
            .scalars()
            .all()
        )
    by_id = {b.internal_id: b for b in bonds}
    lines = [
        f"Рынок: {total} облигаций в базе. По валютам: "
        + ", ".join(f"{cur} — {n}" for cur, n in by_cur)
        + ".",
        "Топ облигаций по скору Aigenis (0-100):",
    ]
    for s in top_scores:
        b = by_id.get(s.internal_id)
        if b is None:
            continue
        ytm = float(b.yield_to_maturity) if b.yield_to_maturity else None
        ytm_s = f"{ytm:.2f}%" if ytm is not None else "Н/Д"
        lines.append(
            f"- {b.internal_id} · {b.name[:60]} · {b.currency} · YTM {ytm_s} · скор {float(s.score):.1f}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Local (keyless) fallback — real data, no external API
# --------------------------------------------------------------------------- #
_BOND_ID_RE = re.compile(r"(?<!\w)([A-Z]{1,4}[-–—]?\d{1,6})(?!\w)", re.IGNORECASE)
# Multi-part ids like "MF-LB-BYN-0335" — match whole tokens of letters/digits/hyphens.
_MULTI_ID_RE = re.compile(r"(?<!\w)([A-Z][A-Z0-9-]{4,})(?!\w)", re.IGNORECASE)
_CURRENCY_CODES = {"BYN", "USD", "EUR", "RUB", "XAU", "XAG", "XPT", "CNY"}


async def _lookup_bond(candidate: str) -> BondORM | None:
    """Find a bond by internal_id or ISIN (case-insensitive)."""
    async with session_scope() as session:
        return (
            await session.execute(
                select(BondORM).where(
                    (BondORM.internal_id == candidate)
                    | (func.upper(BondORM.isin) == candidate.upper())
                )
            )
        ).scalar_one_or_none()


def _extract_bond_id(text: str) -> str | None:
    """Extract a plausible bond id (internal_id style) from free text."""
    m = _BOND_ID_RE.search(text)
    if m:
        cand = re.sub(r"[–—]", "-", m.group(1)).upper()
        if re.sub(r"[\d-]", "", cand) not in _CURRENCY_CODES:
            return cand
    mt = _MULTI_ID_RE.search(text)
    if mt:
        cand = re.sub(r"[–—]", "-", mt.group(1)).upper()
        if re.sub(r"[\d-]", "", cand) not in _CURRENCY_CODES:
            return cand
    return None


def _fmt(v: float | None, suffix: str = "") -> str:
    if v is None:
        return "Н/Д"
    return f"{v:.2f}{suffix}"


async def _fallback_reply(message: str, internal_id: str | None) -> tuple[str, list[str]]:
    """Rule-based assistant over the database. Returns (reply, sources)."""
    text = message.lower().strip()
    sources: list[str] = []

    if internal_id:
        ctx = await _build_bond_context_entries(internal_id)
        if ctx is None:
            return f"Облигация {internal_id} не найдена в базе данных.", []
        sources.append(f"bond:{ctx[0]}")
        return await _fallback_bond_card(ctx[0]), sources

    # Try to extract a bond id from the question itself.
    candidate = _extract_bond_id(text)
    if candidate:
        hit = await _lookup_bond(candidate)
        if hit is not None:
            sources.append(f"bond:{hit.internal_id}")
            return await _fallback_bond_card(hit.internal_id), sources

    if any(k in text for k in ("привет", "здравств", "помощь", "что умеешь", "как работает")):
        return (
            "Я AI-ассистент по облигациям Aigenis Bonds. Я работаю на реальных данных базы.\n\n"
            "Могу рассказать:\n"
            "• про конкретную облигацию — пришлите её ID (например, OP-51) или откройте карточку и спросите;\n"
            "• про скор и рейтинг облигаций;\n"
            "• что сейчас купить — топ по соотношению доходность/риск;\n"
            "• про обзор рынка: сколько облигаций, по валютам.\n\n"
            "Например: «Какие облигации лучше всего купить сейчас?» или «Что с облигацией BYR-3?»",
            sources,
        )

    if any(
        k in text for k in ("купить", "рекомендац", "лучш", "топ", "выгодн", "взять", "что брать")
    ):
        return await _fallback_top_recommendations(), sources

    if any(
        k in text
        for k in ("обзор рынка", "сколько облигаций", "всего", "статистик", "рынок в целом")
    ):
        return await _fallback_market_overview(), sources

    if any(k in text for k in ("курс", "курсы", "валют", "usd/byn", "доллар", "евро")):
        return await _fallback_fx_rates(), sources

    if any(k in text for k in ("скор", "рейтинг", "оценка", "как считается", "как считает")):
        return await _fallback_scoring_explained(), sources

    # Default: point the user at what I can answer.
    return (
        "Я пока не нашёл в вопросе конкретную облигацию или команду. Вот что я умею:\n"
        "• «Что купить?» — топ облигаций по скору;\n"
        "• «Как считается скор?» — объяснение модели скоринга;\n"
        "• «Обзор рынка» — статистика по базе;\n"
        "• ID облигации (например, OP-51) — полная карточка с вердиктом.",
        sources,
    )


async def _fallback_bond_card(internal_id: str) -> str:
    async with session_scope() as session:
        bond = (
            await session.execute(select(BondORM).where(BondORM.internal_id == internal_id))
        ).scalar_one_or_none()
        if bond is None:
            return f"Облигация {internal_id} не найдена в базе данных."
        orm_score = await get_score(session, internal_id)
        cutoff = date.today() - timedelta(days=30)
        history = (
            (
                await session.execute(
                    select(BondHistoryORM)
                    .where(BondHistoryORM.internal_id == internal_id)
                    .where(BondHistoryORM.date >= cutoff)
                    .order_by(BondHistoryORM.date.desc())
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )

    ytm = float(bond.yield_to_maturity) if bond.yield_to_maturity else None
    price = float(bond.price) if bond.price else None
    coupon = float(bond.coupon_rate) if bond.coupon_rate else None

    if orm_score is None:
        score = score_bond(
            internal_id=internal_id,
            yield_to_maturity=ytm,
            currency=bond.currency,
            maturity_date=bond.maturity_date,
            status=bond.status,
            issuer=bond.issuer,
            price=price,
        )
    else:
        score = score_from_orm(orm_score)

    explained = explain_score(score, currency=bond.currency, ytm_pct=ytm)

    lines = [
        f"Облигация {bond.internal_id} — {bond.name}",
        f"Эмитент: {bond.issuer or 'Н/Д'} · Валюта: {bond.currency} · Статус: {bond.status}",
        f"Цена: {_fmt(price)} · YTM: {_fmt(ytm, '%')} · Купон: {_fmt(coupon, '%')}",
        f"Погашение: {bond.maturity_date.isoformat() if bond.maturity_date else 'Н/Д'}",
    ]
    if history:
        lines.append(
            f"За 30 дней цена изменилась с {_fmt(float(history[-1].price) if history[-1].price else None)} "
            f"до {_fmt(float(history[0].price) if history[0].price else None)}."
        )

    lines.append(f"Скор Aigenis: {explained.score:.2f} — тир {explained.tier}.")
    lines.append(f"Вердикт: {explained.verdict} — {explained.summary}")

    lines.append("\nЭто не индивидуальная инвестиционная рекомендация.")
    return "\n".join(lines)


async def _fallback_top_recommendations(top_n: int = 5) -> str:
    async with session_scope() as session:
        scores = (
            (
                await session.execute(
                    select(BondScoreORM).order_by(BondScoreORM.score.desc()).limit(top_n * 2)
                )
            )
            .scalars()
            .all()
        )
        ids = [s.internal_id for s in scores]
        if not ids:
            return "Сейчас в базе нет рассчитанных скоров. Запустите скоринг и попробуйте снова."
        bonds = (
            (await session.execute(select(BondORM).where(BondORM.internal_id.in_(ids))))
            .scalars()
            .all()
        )
    by_id = {b.internal_id: b for b in bonds}
    lines = ["Топ облигаций по скору Aigenis (доходность/риск):"]
    for s in scores[:top_n]:
        b = by_id.get(s.internal_id)
        if b is None:
            continue
        ytm = float(b.yield_to_maturity) if b.yield_to_maturity else None
        lines.append(
            f"{s.score:.1f} · {s.internal_id} · {b.name[:60]} · YTM {_fmt(ytm, '%')} · {b.currency}"
        )
    lines.append(
        "\nПроверьте детали в карточке каждой облигации. Это не инвестиционная рекомендация."
    )
    return "\n".join(lines)


async def _fallback_market_overview() -> str:
    async with session_scope() as session:
        total = (await session.execute(select(func.count()).select_from(BondORM))).scalar_one()
        active = (
            await session.execute(
                select(func.count()).select_from(BondORM).where(BondORM.status == "active")
            )
        ).scalar_one()
        rows = (
            await session.execute(select(BondORM.currency, func.count()).group_by(BondORM.currency))
        ).all()
    lines = [
        f"В базе {total} облигаций, из них активных — {active}.",
        "По валютам: " + ", ".join(f"{cur} — {n}" for cur, n in sorted(rows)),
    ]
    lines.append("Обновляется автоматически. Скоры считаются по модели Aigenis.")
    return "\n".join(lines)


async def _fallback_fx_rates() -> str:
    from notifications.fx_repository import latest_fx, latest_metal

    async with session_scope() as session:
        fx_pairs = ["USD/BYN", "EUR/BYN", "RUB/BYN", "CNY/BYN"]
        rates = {}
        for pair in fx_pairs:
            row = await latest_fx(session, pair)
            if row is not None:
                rates[pair] = float(row.rate)
        metals = {}
        for metal in ("XAU", "XAG", "XPT"):
            row = await latest_metal(session, metal)
            if row is not None:
                metals[metal] = float(row.price)

    lines = []
    if rates:
        lines.append("Актуальные курсы из мониторинга:")
        lines.extend(f"{pair}: {rate:.2f}" for pair, rate in rates.items())
    if metals:
        lines.append(
            "Металлы (BYN за тройскую унцию): "
            + ", ".join(f"{m} — {p:.2f}" for m, p in metals.items())
        )
    if not lines:
        lines.append(
            "Данные по курсам валют пока не собраны — мониторинг ещё не записал ни одного курса."
        )
    lines.append("Курсы обновляются автоматически в трекере валют.")
    return "\n".join(lines)


async def _fallback_scoring_explained() -> str:
    async with session_scope() as session:
        total = (await session.execute(select(func.count()).select_from(BondScoreORM))).scalar_one()
    return (
        "Скор Aigenis — оценка облигации от 0 до 100 по соотношению доходности и риска.\n"
        "Учитываются: доходность к погашению, дюрация и срок, валюта, ликвидность "
        "и надёжность эмитента. По скору присваивается тир (A–D).\n\n"
        f"Сейчас рассчитаны скоры для {total} облигаций. "
        "Спросите «что купить?» — покажу топ, или отправьте ID облигации для разбора."
    )


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #
@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(RequireFeature("access_nlp_chat"))],
)
async def api_chat(req: ChatRequest):
    """NLP-ответ на вопрос пользователя на основе данных облигации."""
    context_parts: list[str] = []
    sources: list[str] = []

    internal_id = (req.context or {}).get("internal_id")
    if internal_id:
        entry = await _build_bond_context_entries(internal_id)
        if entry:
            sources.append(f"bond:{entry[0]}")
            context_parts.append(entry[1])
    elif req.message:
        # A bond id typed in free text gets the same LLM context as the card.
        cand = _extract_bond_id(req.message)
        if cand:
            hit = await _lookup_bond(cand)
            if hit is not None:
                entry = await _build_bond_context_entries(hit.internal_id)
                if entry:
                    sources.append(f"bond:{entry[0]}")
                    context_parts.append(entry[1])

    system_prompt = (
        "Ты аналитик по облигациям для платформы Aigenis Bonds. "
        "Отвечай на русском языке. Используй ТОЛЬКО данные ниже. Не выдумывай. "
        "Если данных недостаточно — скажи об этом. "
        "Давай конкретные рекомендации с цифрами.\n\n"
    )
    if context_parts:
        system_prompt += "ДАННЫЕ ОБЛИГАЦИИ:\n" + "\n\n".join(context_parts) + "\n\n"
    else:
        # No specific bond was mentioned — give the LLM a market snapshot so it
        # can answer general questions with real bonds instead of "no data".
        market = await _build_market_context()
        system_prompt += "ТЕКУЩИЙ РЫНОК:\n" + market + "\n\n"

    reply = await llm_completion(system_prompt, req.message)
    if reply:
        return ChatResponse(reply=reply, sources=sources)

    local_reply, local_sources = await _fallback_reply(req.message, internal_id)
    return ChatResponse(reply=local_reply, sources=local_sources or sources)
