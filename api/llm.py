"""Shared LLM provider chain: OpenRouter -> OpenAI.

Used by the NLP chat and document analysis. Both providers speak the OpenAI
completions format, so a single caller covers both. Returns None when no key
is configured (callers decide their local fallback behaviour).
"""

from __future__ import annotations

import os

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"

LLM_TIMEOUT = httpx.Timeout(90.0, connect=15.0)


async def llm_completion(
    system_prompt: str,
    user_message: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.3,
    user: str | None = None,
) -> str | None:
    """Call OpenRouter, then OpenAI. Returns None when no key is configured.

    ``user`` is a non-empty end-user identifier required by OpenRouter
    (``safety_identifier`` / ``user``). Without it the provider rejects the
    request with ``invalid_request_error: ... requires an end-user identifier``.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    safety_user = (user or "").strip() or "aigenis-bonds-anon"

    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if or_key:
        model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
        try:
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
                resp = await client.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {or_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "user": safety_user,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return None

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()
        try:
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
                resp = await client.post(
                    OPENAI_URL,
                    headers={
                        "Authorization": f"Bearer {openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "user": safety_user,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            return None

    return None
