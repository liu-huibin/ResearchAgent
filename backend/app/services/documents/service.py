"""Application service for documents attached to a chat session."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.session import Session
from app.core.storage import (
    PreparedUpload,
    compute_md5,
    remove_file,
    store_upload,
    store_prepared_upload,
    validate_upload_extension,
    validate_upload_size,
)

logger = logging.getLogger(__name__)


class SessionNotFoundError(LookupError):
    pass


class DocumentNotFoundError(LookupError):
    pass


async def upload_session_document(
    db: AsyncSession,
    session_id: int,
    filename: str | None,
    content: bytes | PreparedUpload,
) -> Document:
    session = await db.get(Session, session_id)
    if not session:
        raise SessionNotFoundError("会话不存在")

    if isinstance(content, PreparedUpload):
        extension = content.extension
        size_mb = content.size_mb
        file_md5 = content.file_md5
        file_path = store_prepared_upload(content, "1", "sessions", str(session_id))
    else:
        extension = validate_upload_extension(filename)
        size_mb = validate_upload_size(content)
        file_md5 = compute_md5(content)
        file_path = store_upload(
            content,
            extension,
            "1",
            "sessions",
            str(session_id),
        )
    logger.info(
        "Session document upload: session=%d, file=%s, size=%.2fMB",
        session_id,
        filename,
        size_mb,
    )

    try:
        document = Document(
            user_id=1,
            filename=filename or "unknown",
            file_path=file_path,
            file_md5=file_md5,
            type="session",
            session_id=session_id,
        )
        db.add(document)
        await db.flush()
        await db.refresh(document)

        session.active_document_id = document.id
        db.add(session)
        await db.commit()
        return document
    except Exception:
        await db.rollback()
        try:
            remove_file(file_path)
        except OSError:
            logger.warning(
                "Failed to remove rolled-back session upload: %s",
                file_path,
                exc_info=True,
            )
        raise


async def get_session_document(
    db: AsyncSession,
    session_id: int,
) -> Document | None:
    session = await db.get(Session, session_id)
    if not session or not session.active_document_id:
        return None
    return await db.get(Document, session.active_document_id)


async def get_document(db: AsyncSession, document_id: int) -> Document:
    document = await db.get(Document, document_id)
    if not document:
        raise DocumentNotFoundError("文档不存在")
    return document
