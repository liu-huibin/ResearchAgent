"""Knowledge-base ingestion and deletion orchestration."""

import asyncio
import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.document import Document
from app.core.config import settings
from app.services.bm25_index import add_to_index as add_to_bm25
from app.services.bm25_index import remove_from_index as remove_from_bm25
from app.services.chunking import chunk_document
from app.services.embedding import embed_documents
from app.services.file_parser import extract_text_from_file
from app.core.storage import (
    PreparedUpload,
    compute_md5,
    remove_file,
    store_upload,
    store_prepared_upload,
    validate_upload_extension,
    validate_upload_size,
)
from app.services.vectordb import delete_document as delete_vectordb_doc
from app.services.vectordb import index_document

logger = logging.getLogger(__name__)


class DuplicateKnowledgeError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    pass


class KnowledgeNotFoundError(LookupError):
    pass


class KnowledgeProcessingError(RuntimeError):
    pass


async def upload_knowledge(
    db: AsyncSession,
    filename: str | None,
    content: bytes | PreparedUpload,
) -> Document:
    if isinstance(content, PreparedUpload):
        extension = content.extension
        size_mb = content.size_mb
        file_md5 = content.file_md5
    else:
        extension = validate_upload_extension(filename)
        size_mb = validate_upload_size(content)
        file_md5 = compute_md5(content)
    logger.info(
        "Knowledge upload: size=%.2fMB, md5=%s",
        size_mb,
        file_md5,
    )

    result = await db.execute(
        select(Document).where(
            Document.file_md5 == file_md5,
            Document.type == "knowledge",
        )
    )
    if result.scalars().first():
        raise DuplicateKnowledgeError("文件已存在于知识库中")

    file_path = (
        store_prepared_upload(content, "1", "knowledge")
        if isinstance(content, PreparedUpload)
        else store_upload(content, extension, "1", "knowledge")
    )
    document = Document(
        user_id=1,
        filename=filename or "unknown",
        file_path=file_path,
        file_md5=file_md5,
        type="knowledge",
        session_id=None,
    )
    try:
        db.add(document)
        await db.flush()
        await db.refresh(document)

        text = await asyncio.to_thread(
            extract_text_from_file,
            file_path,
            settings.max_extracted_chars,
        )
        if not text.strip():
            raise EmptyDocumentError("无法从此文件中提取文本，可能为扫描件或图片PDF")

        chunks = chunk_document(text, filename=document.filename, doc_id=document.id)
        if chunks:
            embeddings = await asyncio.to_thread(
                embed_documents,
                [chunk["content"] for chunk in chunks],
            )
            await asyncio.to_thread(index_document, chunks, embeddings)
            try:
                await asyncio.to_thread(add_to_bm25, "knowledge_base", chunks)
            except Exception:
                logger.warning(
                    "BM25 index build failed for knowledge upload, doc_id=%d",
                    document.id,
                    exc_info=True,
                )
        await db.commit()
        logger.info(
            "Knowledge upload complete: doc_id=%d, chunks=%d",
            document.id,
            len(chunks),
        )
        return document
    except (EmptyDocumentError, DuplicateKnowledgeError):
        await cleanup_failed_upload(db, document, file_path)
        raise
    except Exception as exc:
        logger.exception("Document processing failed for knowledge upload")
        await cleanup_failed_upload(db, document, file_path)
        raise KnowledgeProcessingError("文档处理失败") from exc


async def cleanup_failed_upload(
    db: AsyncSession,
    document: Document,
    file_path: str,
) -> None:
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
    try:
        remove_file(file_path)
    except OSError:
        logger.warning(
            "Failed to remove rolled-back knowledge upload: %s",
            file_path,
            exc_info=True,
        )


async def remove_knowledge(db: AsyncSession, doc_id: int) -> None:
    document = await db.get(Document, doc_id)
    if not document or document.type != "knowledge":
        raise KnowledgeNotFoundError("知识库文档不存在")

    logger.info(
        "Knowledge doc deleting: doc_id=%d, file=%s",
        doc_id,
        document.filename,
    )
    if os.path.exists(document.file_path):
        remove_file(document.file_path)

    try:
        delete_vectordb_doc(doc_id)
    except Exception:
        logger.warning(
            "Vectordb delete failed during knowledge remove: doc_id=%d",
            doc_id,
            exc_info=True,
        )
    try:
        remove_from_bm25("knowledge_base", doc_id)
    except Exception:
        logger.warning(
            "BM25 remove failed during knowledge remove: doc_id=%d",
            doc_id,
            exc_info=True,
        )

    await db.delete(document)
    await db.commit()


async def list_knowledge(db: AsyncSession) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.type == "knowledge")
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())
