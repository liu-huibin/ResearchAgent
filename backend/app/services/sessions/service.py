"""Session persistence and cleanup orchestration."""

import logging
import os

from sqlalchemy import delete as sql_delete
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import desc, select

from app.models.document import Document
from app.models.message import Message
from app.models.session import Session
from app.models.workflow_run import WorkflowRun
from app.core.storage import remove_empty_session_directory, remove_file

logger = logging.getLogger(__name__)


class SessionNotFoundError(LookupError):
    pass


async def create_session(db: AsyncSession, title: str) -> Session:
    session = Session(title=title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(db: AsyncSession) -> list[Session]:
    result = await db.execute(select(Session).order_by(desc(Session.updated_at)))
    return list(result.scalars().all())


async def delete_session(db: AsyncSession, session_id: int) -> None:
    session = await db.get(Session, session_id)
    if not session:
        raise SessionNotFoundError("会话不存在")

    try:
        result = await db.execute(
            select(Document).where(Document.session_id == session_id)
        )
        session_documents = result.scalars().all()
        file_paths = [document.file_path for document in session_documents]

        await db.execute(
            sql_update(Session)
            .where(Session.id == session_id)
            .values(active_document_id=None)
        )
        await db.execute(
            sql_delete(WorkflowRun).where(WorkflowRun.session_id == session_id)
        )
        await db.execute(
            sql_delete(Message).where(Message.session_id == session_id)
        )
        await db.execute(
            sql_delete(Document).where(Document.session_id == session_id)
        )
        db.expunge(session)
        await db.execute(sql_delete(Session).where(Session.id == session_id))
        await db.commit()

        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    remove_file(file_path)
            except OSError:
                logger.warning(
                    "Failed to remove session file: %s",
                    file_path,
                    exc_info=True,
                )
        remove_empty_session_directory(session_id)
    except Exception:
        await db.rollback()
        raise


async def update_session(
    db: AsyncSession,
    session_id: int,
    update_data: dict,
) -> Session:
    session = await db.get(Session, session_id)
    if not session:
        raise SessionNotFoundError("会话不存在")
    for key, value in update_data.items():
        setattr(session, key, value)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session
