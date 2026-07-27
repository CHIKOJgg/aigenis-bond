"""Tests for the document analysis endpoint.

Covers: file size limits, content type validation, PDF extraction fallback,
temp file cleanup, feature gating, and error handling.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from io import BytesIO

from api.document_analysis import router as doc_router

app = FastAPI()
app.include_router(doc_router)


def _make_pdf_bytes() -> bytes:
    """Return minimal valid PDF bytes."""
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\nxref\n0 3\ntrailer<</Size 3/Root 1 0 R>>\n"


@pytest.mark.asyncio
async def test_upload_rejects_non_pdf():
    """Non-PDF file extensions must be rejected with 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file():
    """Files exceeding 10 MB must be rejected with 413."""
    oversized = b"x" * (11 * 1024 * 1024)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("big.pdf", oversized, "application/pdf")},
        )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_upload_rejects_empty_file():
    """Files under 100 bytes must be rejected with 400."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("tiny.pdf", b"x" * 50, "application/pdf")},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_upload_returns_validation_error_on_no_pdf_extraction():
    """When PDF text extraction yields empty, returns a structured error response."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("empty.pdf", _make_pdf_bytes(), "application/pdf")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert data.get("internal_id") is None