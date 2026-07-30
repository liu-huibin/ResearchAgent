import hashlib
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select as sm_select

from app.config import settings
from app.database import get_session
from app.models.document import Document
from app.schemas.document import DocumentResponse
from app.services.chunking import chunk_document
from app.services.embedding import embed_documents
from app.services.file_parser import extract_text_from_file
from app.services.bm25_index import add_to_index as add_to_bm25
from app.services.bm25_index import remove_from_index as remove_from_bm25
from app.services.vectordb import delete_document as delete_vectordb_doc
from app.services.vectordb import index_document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx"}


@router.post("/upload", response_model=DocumentResponse)
async def upload_knowledge(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
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

    file_md5 = hashlib.md5(content).hexdigest()
    logger.info("Knowledge upload: file=%s, size=%.2fMB, md5=%s", file.filename, file_size_mb, file_md5)

    result = await db.execute(
        sm_select(Document).where(
            Document.file_md5 == file_md5,
            Document.type == "knowledge",
        )
    )
    if result.scalars().first():
        logger.warning("Duplicate knowledge file rejected: %s", file.filename)
        raise HTTPException(status_code=409, detail="文件已存在于知识库中")

    user_dir = os.path.join(settings.upload_dir, "1", "knowledge")
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
        type="knowledge",
        session_id=None,
    )
    db.add(document)
    await db.flush()
    await db.refresh(document)

    try:
        text = extract_text_from_file(file_path, max_chars=None)
        if not text.strip():
            raise HTTPException(status_code=400, detail="无法从此文件中提取文本，可能为扫描件或图片PDF")

        chunks = chunk_document(text, filename=document.filename, doc_id=document.id)
        if chunks:
            chunk_texts = [c["content"] for c in chunks]
            logger.info("Generating embeddings for %d chunks", len(chunks))
            embeddings = embed_documents(chunk_texts)
            index_document(chunks, embeddings)
            try:
                add_to_bm25("knowledge_base", chunks)
            except Exception:
                logger.warning("BM25 index build failed for knowledge upload, doc_id=%d", document.id, exc_info=True)
        await db.commit()
        logger.info("Knowledge upload complete: doc_id=%d, chunks=%d", document.id, len(chunks))
    except HTTPException:
        await _cleanup_failed_upload(db, document, file_path)
        raise
    except Exception as e:
        logger.exception("Document processing failed for knowledge upload: %s", file.filename)
        await _cleanup_failed_upload(db, document, file_path)
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")

    return document


async def _cleanup_failed_upload(
    db: AsyncSession,
    document: Document,
    file_path: str,
) -> None:
    """Roll back database state and best-effort external indexes/files."""
    await db.rollback()
    if document.id is not None:
        try:
            delete_vectordb_doc(document.id)
        except Exception:
            logger.warning(
                "Vectordb rollback failed: doc_id=%d",
                document.id,
                exc_info=True,
            )
        try:
            remove_from_bm25("knowledge_base", document.id)
        except Exception:
            logger.warning(
                "BM25 rollback failed: doc_id=%d",
                document.id,
                exc_info=True,
            )
    if os.path.exists(file_path):
        os.remove(file_path)


@router.delete("/{doc_id}", status_code=204)
async def remove_knowledge(
    doc_id: int,
    db: AsyncSession = Depends(get_session),
):
    doc = await db.get(Document, doc_id)
    if not doc or doc.type != "knowledge":
        raise HTTPException(status_code=404, detail="知识库文档不存在")

    logger.info("Knowledge doc deleting: doc_id=%d, file=%s", doc_id, doc.filename)

    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    try:
        delete_vectordb_doc(doc_id)
    except Exception:
        logger.warning("Vectordb delete failed during knowledge remove: doc_id=%d", doc_id, exc_info=True)

    try:
        remove_from_bm25("knowledge_base", doc_id)
    except Exception:
        logger.warning("BM25 remove failed during knowledge remove: doc_id=%d", doc_id, exc_info=True)

    await db.delete(doc)
    await db.commit()
    logger.info("Knowledge doc deleted: doc_id=%d", doc_id)


@router.get("/list", response_model=list[DocumentResponse])
async def list_knowledge(db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        sm_select(Document).where(Document.type == "knowledge").order_by(Document.created_at.desc())
    )
    return result.scalars().all()
