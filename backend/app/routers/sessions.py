import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.session import (
    SessionCreate,
    SessionListItem,
    SessionResponse,
    SessionUpdate,
)
from app.services.sessions.service import (
    SessionNotFoundError,
    create_session as create_session_record,
    delete_session as delete_session_record,
    list_sessions as fetch_sessions,
    update_session as update_session_record,
)
from app.core.storage import (
    remove_empty_session_directory as _remove_empty_session_directory,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_session),
):
    return await create_session_record(db, body.title)


@router.get("", response_model=list[SessionListItem])
async def list_sessions(db: AsyncSession = Depends(get_session)):
    return await fetch_sessions(db)


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_session),
):
    try:
        await delete_session_record(db, session_id)
        logger.info("Deleted session %d and related data", session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to delete session %d", session_id)
        raise HTTPException(status_code=500, detail=f"删除失败: {exc}") from exc


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: int,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_session),
):
    try:
        return await update_session_record(
            db,
            session_id,
            body.model_dump(exclude_unset=True),
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
