import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update as sql_update, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, desc

from app.database import get_session
from app.models.session import Session
from app.models.message import Message
from app.models.document import Document
from app.schemas.session import SessionCreate, SessionUpdate, SessionResponse, SessionListItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


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
        # Step 1: Bulk-detach documents that reference this session
        await db.execute(
            sql_update(Document)
            .where(Document.session_id == session_id)
            .values(session_id=None)
        )

        # Step 2: Clear active_document_id on the session
        await db.execute(
            sql_update(Session)
            .where(Session.id == session_id)
            .values(active_document_id=None)
        )

        # Step 3: Bulk-delete related messages
        await db.execute(
            sql_delete(Message).where(Message.session_id == session_id)
        )

        # Step 4: Expunge session from ORM identity map, then delete via Core
        db.expunge(session)
        await db.execute(
            sql_delete(Session).where(Session.id == session_id)
        )

        await db.commit()
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
