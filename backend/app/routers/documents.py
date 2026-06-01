import hashlib
import logging
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models.document import Document
from app.models.session import Session
from app.schemas.document import DocumentResponse
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}


def compute_md5(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


@router.post("/sessions/{session_id}/upload", response_model=DocumentResponse)
async def upload_session_document(
    session_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}，仅支持 PDF/Word")

    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过限制 ({settings.max_upload_size_mb}MB)",
        )

    file_md5 = compute_md5(content)
    logger.info("Session document upload: session=%d, file=%s, size=%.2fMB", session_id, file.filename, file_size_mb)

    user_dir = os.path.join(settings.upload_dir, "1", "sessions", str(session_id))
    os.makedirs(user_dir, exist_ok=True)

    safe_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(user_dir, safe_filename)

    with open(file_path, "wb") as f:
        f.write(content)

    document = Document(
        user_id=1,
        filename=file.filename or "unknown",
        file_path=file_path,
        file_md5=file_md5,
        type="session",
        session_id=session_id,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    session.active_document_id = document.id
    db.add(session)
    await db.commit()

    return document


@router.get("/sessions/{session_id}/document", response_model=DocumentResponse | None)
async def get_session_document(
    session_id: int, db: AsyncSession = Depends(get_session)
):
    session = await db.get(Session, session_id)
    if not session or not session.active_document_id:
        return None
    doc = await db.get(Document, session.active_document_id)
    return doc


@router.get("/documents/{document_id}/file")
async def serve_document_file(
    document_id: int, db: AsyncSession = Depends(get_session)
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    media_type = "application/pdf"
    if doc.filename.endswith((".doc", ".docx")):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return FileResponse(doc.file_path, media_type=media_type, filename=doc.filename)
