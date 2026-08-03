"""Tests for the document analysis endpoint.

Covers: file size limits, content type validation, PDF extraction fallback,
temp file cleanup, feature gating, and error handling.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.auth.service import create_access_token
from api.document_analysis import router as doc_router
from scraper.db import session_scope
from scraper.orm import UserORM

app = FastAPI()
app.include_router(doc_router)

# Pro-tier user used by the upload tests (document analysis is a Pro feature).
_PRO_USER_ID = 9099


@pytest.fixture(autouse=True)
def _clean_upload_store():
    """The per-user upload budget is module-global; reset it between tests."""
    import api.document_analysis as doc

    doc._upload_store.clear()
    yield
    doc._upload_store.clear()


async def _pro_headers() -> dict[str, str]:
    async with session_scope() as s:
        await s.merge(
            UserORM(
                id=_PRO_USER_ID,
                email="doc-pro@example.com",
                name="Doc",
                password_hash="x",
                is_active=True,
                subscription_tier="pro",
            )
        )
    return {"Authorization": f"Bearer {create_access_token(_PRO_USER_ID)}"}


def _make_pdf_bytes() -> bytes:
    """Return minimal valid PDF bytes."""
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\nxref\n0 3\ntrailer<</Size 3/Root 1 0 R>>\n"


@pytest.mark.asyncio
async def test_upload_rejects_anonymous():
    """Anonymous uploads must be rejected (feature requires auth + Pro)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
        )
    assert resp.status_code in (401, 402)


@pytest.mark.asyncio
async def test_upload_rejects_non_pdf():
    """Non-PDF file extensions must be rejected with 400."""
    headers = await _pro_headers()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
            headers=headers,
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file():
    """Files exceeding 10 MB must be rejected with 413."""
    oversized = b"x" * (11 * 1024 * 1024)
    headers = await _pro_headers()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("big.pdf", oversized, "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_upload_rejects_empty_file():
    """Files under 100 bytes must be rejected with 400."""
    headers = await _pro_headers()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("tiny.pdf", b"x" * 50, "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_returns_validation_error_on_no_pdf_extraction():
    """When PDF text extraction yields empty, returns a structured error response."""
    headers = await _pro_headers()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("empty.pdf", _make_pdf_bytes(), "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert data.get("internal_id") is None


@pytest.mark.asyncio
async def test_upload_persists_and_lists(monkeypatch):
    """Successful analysis is persisted and appears in the listing."""
    import api.document_analysis as doc

    def fake_extract(_path: str) -> str:
        return "Эмитент: Пример. Купон: 12%. Погашение: 2030."

    async def fake_analyze(_text: str) -> dict:
        return {
            "summary": "Хороший проспект.",
            "extracted": {"issuer": "Пример"},
            "risk_flags": ["Ковенант на изменение контроля"],
        }

    monkeypatch.setattr(doc, "_extract_text_from_pdf", fake_extract)
    monkeypatch.setattr(doc, "_analyze_with_llm", fake_analyze)

    headers = await _pro_headers()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("ok.pdf", _make_pdf_bytes(), "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] > 0, "upload must persist and return a real row id"
    assert data["summary"] == "Хороший проспект."
    assert data["risk_flags"] == ["Ковенант на изменение контроля"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listing = await client.get("/api/v1/documents", headers=headers)
    assert listing.status_code == 200
    rows = listing.json()
    assert any(r["id"] == data["id"] and r["filename"] == "ok.pdf" for r in rows)


@pytest.mark.asyncio
async def test_upload_is_rate_limited_per_user(monkeypatch):
    """More than the hourly budget of uploads returns 429."""
    import api.document_analysis as doc

    monkeypatch.setattr(doc, "_UPLOAD_MAX_PER_WINDOW", 3)
    monkeypatch.setattr(doc, "_extract_text_from_pdf", lambda p: "")
    headers = await _pro_headers()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(3):
            resp = await client.post(
                "/api/v1/documents/upload",
                files={"file": ("r.pdf", _make_pdf_bytes(), "application/pdf")},
                headers=headers,
            )
            assert resp.status_code == 200
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("r.pdf", _make_pdf_bytes(), "application/pdf")},
            headers=headers,
        )
    assert resp.status_code == 429
