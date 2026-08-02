"""Document analysis endpoint — upload and analyze bond prospectuses.

Gated behind `access_document_analysis` (Pro/Enterprise). Extracts text from
PDF, sends to LLM for structured parsing of bond parameters. Successful
analyses are persisted per user (document_analysis table, migration 0020)
and can be listed back via GET /api/v1/documents.
"""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
import threading
import time
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from api.access_control import RequireFeature, require_user_id
from scraper.db import session_scope
from scraper.orm import DocumentAnalysisORM

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_UPLOAD_MAX_PER_WINDOW = 10
_UPLOAD_WINDOW_SECONDS = 3600
_UPLOAD_MAX_TRACKED_USERS = 20_000  # bound memory: evict stale entries
_upload_store: dict[int, list[float]] = {}
_upload_lock = threading.Lock()

router = APIRouter(prefix="/api/v1", tags=["documents"])


def _upload_rate_check(user_id: int) -> bool:
    now = time.monotonic()
    with _upload_lock:
        # Periodic cleanup to prevent unbounded memory growth.
        if len(_upload_store) > _UPLOAD_MAX_TRACKED_USERS:
            for key in [k for k in _upload_store if not _upload_store[k] or _upload_store[k][-1] <= now - _UPLOAD_WINDOW_SECONDS]:
                _upload_store.pop(key, None)
        hits = [t for t in _upload_store.get(user_id, []) if t > now - _UPLOAD_WINDOW_SECONDS]
        if len(hits) >= _UPLOAD_MAX_PER_WINDOW:
            _upload_store[user_id] = hits
            return False
        hits.append(now)
        _upload_store[user_id] = hits
        return True


class DocumentAnalysisResult(BaseModel):
    id: int
    filename: str
    internal_id: str | None
    summary: str
    extracted: dict[str, object]
    risk_flags: list[str]
    created_at: str


def _extract_text_from_pdf(file_path: str) -> str:
    """Extract text from PDF using available library.

    Corrupted/encrypted PDFs raise inside the reader (not at import time), so
    those exceptions are caught too and treated as "no text" — a broken file
    must never 500 the endpoint.
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        try:
            text = ""
            for page in doc:
                text += page.get_text()
            return text[:15000]  # limit for LLM context
        finally:
            doc.close()
    except Exception:  # import error OR corrupted/encrypted file
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(file_path)
            text = ""
            for page in reader.pages[:20]:
                text += page.extract_text() or ""
            return text[:15000]
        except Exception:
            return ""


def _analyze_with_llm(text: str) -> dict[str, object]:
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
    user_id: int = Depends(require_user_id),
):
    """Upload and analyze a bond prospectus PDF (persisted per user)."""
    if not _upload_rate_check(user_id):
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много загрузок. Максимум: {_UPLOAD_MAX_PER_WINDOW} в час.",
        )

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Только PDF-файлы поддерживаются")

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Файл слишком большой. Максимум: {_MAX_UPLOAD_BYTES // (1024 * 1024)} МБ.",
        )
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="Файл слишком мал или повреждён.")
    # Verify PDF magic bytes — the extension alone is not proof of format.
    if not content.lstrip().startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Файл не является PDF (неверные магические байты).")

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        text = _extract_text_from_pdf(tmp_path)
        if not text.strip():
            return DocumentAnalysisResult(
                id=0,
                filename=file.filename,
                internal_id=None,
                summary="Не удалось извлечь текст из PDF.",
                extracted={},
                risk_flags=[],
                created_at=datetime.now().isoformat(),
            ).model_dump()

        analysis = _analyze_with_llm(text)
        extracted = dict(analysis.get("extracted") or {})
        risk_flags = list(analysis.get("risk_flags") or [])

        now = datetime.now()
        async with session_scope() as session:
            row = DocumentAnalysisORM(
                user_id=user_id,
                filename=file.filename,
                internal_id=None,
                ai_summary=str(analysis.get("summary", "")),
                extracted_data=extracted,
                risk_flags=risk_flags,
            )
            session.add(row)
            await session.flush()
            row_id = row.id

        return DocumentAnalysisResult(
            id=row_id,
            filename=file.filename,
            internal_id=None,
            summary=str(analysis.get("summary", "")),
            extracted=extracted,
            risk_flags=risk_flags,
            created_at=now.isoformat(),
        ).model_dump()
    finally:
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


@router.get(
    "/documents",
    dependencies=[Depends(RequireFeature("access_document_analysis"))],
)
async def api_list_documents(
    user_id: int = Depends(require_user_id),
):
    """List uploaded documents for the current user."""
    async with session_scope() as session:
        result = await session.execute(
            select(DocumentAnalysisORM)
            .where(DocumentAnalysisORM.user_id == user_id)
            .order_by(DocumentAnalysisORM.created_at.desc())
        )
        rows = result.scalars().all()

    return [
        {
            "id": r.id,
            "filename": r.filename,
            "internal_id": r.internal_id,
            "summary": r.ai_summary,
            "extracted": r.extracted_data or {},
            "risk_flags": r.risk_flags or [],
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]
