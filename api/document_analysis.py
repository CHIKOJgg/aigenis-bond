"""Document analysis endpoint — upload and analyze bond prospectuses.

Gated behind `access_document_analysis` (Pro/Enterprise). Extracts text from
PDF, sends to LLM for structured parsing of bond parameters.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from api.access_control import RequireFeature, get_optional_user_id
from scraper.db import session_scope
from scraper.orm import Base

router = APIRouter(prefix="/api/v1", tags=["documents"])


# ---------------------------------------------------------------------------
# ORM model (created inline — will be migrated via alembic separately)
# ---------------------------------------------------------------------------
def _ensure_document_model():
    """Lazy-import or create the DocumentAnalysis model if table exists."""
    try:
        from scraper.orm import DocumentAnalysisORM
        return DocumentAnalysisORM
    except ImportError:
        return None


class DocumentAnalysisResult(BaseModel):
    id: int
    filename: str
    internal_id: str | None
    summary: str
    extracted: dict[str, Any]
    risk_flags: list[str]
    created_at: str


def _extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF using available library."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text[:15000]  # limit for LLM context
    except ImportError:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages[:20]:
                text += page.extract_text() or ""
            return text[:15000]
        except ImportError:
            return ""


def _analyze_with_llm(text: str) -> dict[str, Any]:
    """Send extracted text to LLM for structured analysis."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {
            "summary": "AI-анализ недоступен: API-ключ не настроен.",
            "extracted": {},
            "risk_flags": [],
        }

    prompt = (
        "Проанализируй проспект облигации. Извлеки:\n"
        "- Эмитент\n- Номинал\n- Купон (ставка, тип, частота)\n"
        "- Дата погашения\n- Оферта (дата, цена)\n- Обеспечение\n"
        "- Ковенанты (список)\n- Рейтинг\n- Особые условия\n- Риски (список)\n\n"
        "Ответ в JSON: {\"summary\": \"...\", \"extracted\": {...}, \"risk_flags\": [...]}\n"
        "Текст проспекта:\n" + text[:12000]
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты аналитик облигаций. Отвечай строго в JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.1,
        )
        content = response.choices[0].message.content or "{}"
        # Try to extract JSON from response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(content[start:end])
    except Exception:
        pass

    return {
        "summary": "Не удалось проанализировать документ.",
        "extracted": {},
        "risk_flags": [],
    }


@router.post(
    "/documents/upload",
    dependencies=[Depends(RequireFeature("access_document_analysis"))],
)
async def api_upload_document(
    file: UploadFile = File(...),
    user_id: int | None = Depends(get_optional_user_id),
):
    """Upload and analyze a bond prospectus PDF."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Только PDF-файлы поддерживаются")

    # Save to temp file
    suffix = ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        text = _extract_text_from_pdf(tmp_path)
        if not text.strip():
            return {
                "id": 0,
                "filename": file.filename,
                "internal_id": None,
                "summary": "Не удалось извлечь текст из PDF.",
                "extracted": {},
                "risk_flags": [],
                "created_at": datetime.now().isoformat(),
            }

        analysis = _analyze_with_llm(text)

        return {
            "id": 0,
            "filename": file.filename,
            "internal_id": None,
            "summary": analysis.get("summary", ""),
            "extracted": analysis.get("extracted", {}),
            "risk_flags": analysis.get("risk_flags", []),
            "created_at": datetime.now().isoformat(),
        }
    finally:
        os.unlink(tmp_path)


@router.get(
    "/documents",
    dependencies=[Depends(RequireFeature("access_document_analysis"))],
)
async def api_list_documents(
    user_id: int | None = Depends(get_optional_user_id),
):
    """List uploaded documents for the current user."""
    Model = _ensure_document_model()
    if Model is None:
        return []

    async with session_scope() as session:
        uid = user_id or 0
        result = await session.execute(
            select(Model).where(Model.user_id == uid).order_by(Model.created_at.desc())
        )
        rows = result.scalars().all()

    return [
        {
            "id": r.id,
            "filename": r.filename,
            "internal_id": r.internal_id,
            "summary": r.ai_summary,
            "extracted": r.extracted_data,
            "risk_flags": r.risk_flags or [],
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]
