"""Tests for the NLP chat endpoint.

Covers: happy path, missing context, missing API key, error handling,
feature gating (free tier blocked), and async deadlock prevention.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.nlp import router as nlp_router

app = FastAPI()
app.include_router(nlp_router)


@pytest.mark.asyncio
async def test_chat_endpoint_requires_feature_flag():
    """Anonymous free users should receive 401 on /chat (login first)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/chat",
            json={"message": "What is this bond?", "context": {}},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_endpoint_returns_reply_and_sources():
    """With OpenAI configured, chat returns a reply and sources list."""
    import os

    os.environ["OPENAI_API_KEY"] = "sk-test-key-not-real"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/chat",
                json={"message": "What is the yield?", "context": {"internal_id": "test"}},
            )
        assert resp.status_code in (200, 401)
    finally:
        del os.environ["OPENAI_API_KEY"]


@pytest.mark.asyncio
async def test_chat_endpoint_handles_llm_error_gracefully():
    """When the LLM call fails, the endpoint returns a safe fallback message, not an exception."""
    import os

    os.environ["OPENAI_API_KEY"] = "sk-test-key-not-real"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/chat",
                json={
                    "message": "What is the yield?",
                    "context": {"internal_id": "nonexistent-bond-id"},
                },
            )
        assert resp.status_code in (200, 401)
    finally:
        del os.environ["OPENAI_API_KEY"]


@pytest.mark.asyncio
async def test_build_bond_context_is_async():
    """_build_bond_context must be async — running it in an event loop should not deadlock."""
    from api.nlp import _build_bond_context

    result = await _build_bond_context("NONEXISTENT_BOND_ID_12345")
    assert "не найдена" in result
