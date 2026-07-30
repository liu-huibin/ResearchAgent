import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update as sql_update, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc

from app.config import settings
from app.database import get_session
from app.models.session import Session
from app.models.message import Message
from app.models.document import Document
from app.models.workflow_run import WorkflowRun
from app.schemas.session import SessionCreate, SessionUpdate, SessionResponse, SessionListItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _remove_empty_session_directory(session_id: int) -> None:
    """Remove only this session's expected upload directory when it is empty."""
    sessions_root = os.path.realpath(
        os.path.abspath(os.path.join(settings.upload_dir, "1", "sessions"))
    )
    session_dir = os.path.realpath(
        os.path.abspath(os.path.join(sessions_root, str(session_id)))
    )

    try:
        is_expected_child = (
            session_dir != sessions_root
            and os.path.commonpath([sessions_root, session_dir]) == sessions_root
        )
    except ValueError:
        is_expected_child = False

    if not is_expected_child:
        logger.error(
            "Refusing to remove unexpected session directory: %s",
            session_dir,
        )
        return

    try:
        # os.rmdir is deliberately non-recursive: unknown files are preserved.
        os.rmdir(session_dir)
    except FileNotFoundError:
        return
    except OSError:
        logger.info(
            "Session directory retained because it is not empty or cannot be removed: %s",
            session_dir,
        )


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: SessionCreate, db: AsyncSession = Depends(get_session)
):
    session = Session(title=body.title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("", response_model=list[SessionListItem])
async def list_sessions(db: AsyncSession = Depends(get_session)):
    result = await db.execute(
        select(Session).order_by(desc(Session.updated_at))
    )
    return result.scalars().all()


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: int, db: AsyncSession = Depends(get_session)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    try:
        result = await db.execute(
            select(Document).where(Document.session_id == session_id)
        )
        session_documents = result.scalars().all()
        file_paths = [doc.file_path for doc in session_documents]

        # Break the circular FK before deleting session documents.
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
        await db.execute(
            sql_delete(Session).where(Session.id == session_id)
        )

        await db.commit()

        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError:
                logger.warning(
                    "Failed to remove session file: %s",
                    file_path,
                    exc_info=True,
                )
        _remove_empty_session_directory(session_id)
        logger.info(f"Deleted session {session_id} and related data")

    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: int, body: SessionUpdate, db: AsyncSession = Depends(get_session)
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(session, key, value)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session
