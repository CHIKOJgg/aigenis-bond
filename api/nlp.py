"""NLP chat endpoint — AI assistant for bond questions.

Gated behind `access_nlp_chat` (Pro/Enterprise). Uses OpenAI API to answer
user questions about bonds using real market data as context.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.access_control import RequireFeature, get_optional_user_id
from api import _helpers as _h
from scraper.db import session_scope
from scraper.orm import BondORM, BondScoreORM, BondHistoryORM
from sqlalchemy import select
from datetime import date, timedelta

router = APIRouter(prefix="/api/v1", tags=["nlp"])


class ChatRequest(BaseModel):
    message: str
    context: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    reply: str
    sources: list[str] = []


def _build_bond_context(internal_id: str) -> str:
    """Load bond data and build context string for the LLM."""
    import asyncio

    async def _load():
        async with session_scope() as session:
            bond = (
                await session.execute(
                    select(BondORM).where(BondORM.internal_id == internal_id)
                )
            ).scalar_one_or_none()
            if bond is None:
                return None

            score = (
                await session.execute(
                    select(BondScoreORM).where(BondScoreORM.internal_id == internal_id)
                )
            ).scalar_one_or_none()

            cutoff = date.today() - timedelta(days=30)
            history = (
                await session.execute(
                    select(BondHistoryORM)
                    .where(BondHistoryORM.internal_id == internal_id)
                    .where(BondHistoryORM.date >= cutoff)
                    .order_by(BondHistoryORM.date.desc())
                    .limit(10)
                )
            ).scalars().all()

            return bond, score, history

    try:
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(_load())
    except RuntimeError:
        import asyncio
        result = asyncio.run(_load())

    if result is None:
        return f"Облигация {internal_id} не найдена в базе данных."

    bond, score, history = result
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
        lines.append(f"Цена 30 дней назад: {float(history[-1].price) if history[-1].price else 'Н/Д'}")
        lines.append(f"Цена сейчас: {float(history[0].price) if history[0].price else 'Н/Д'}")

    return "\n".join(lines)


def _call_llm(system_prompt: str, user_message: str) -> str:
    """Call OpenAI API (or return a fallback if not configured)."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return (
            "AI-ассистент временно недоступен. API-ключ OpenAI не настроен. "
            "Обратитесь к администратору."
        )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1024,
            temperature=0.3,
        )
        return response.choices[0].message.content or "Не удалось получить ответ."
    except Exception as e:
        return f"Ошибка при обращении к AI: {type(e).__name__}"


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
        bond_ctx = _build_bond_context(internal_id)
        context_parts.append(bond_ctx)
        sources.append(f"bond:{internal_id}")

    system_prompt = (
        "Ты аналитик по облигациям для платформы Aigenis Bonds. "
        "Отвечай на русском языке. Используй ТОЛЬКО данные ниже. Не выдумывай. "
        "Если данных недостаточно — скажи об этом. "
        "Давай конкретные рекомендации с цифрами.\n\n"
    )
    if context_parts:
        system_prompt += "ДАННЫЕ ОБЛИГАЦИИ:\n" + "\n\n".join(context_parts) + "\n\n"

    reply = _call_llm(system_prompt, req.message)
    return ChatResponse(reply=reply, sources=sources)
