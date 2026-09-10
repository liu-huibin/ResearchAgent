from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.message import MessageCreate, MessageResponse
from app.schemas.metrics import SessionMetricsResponse
from app.services.chat.service import (
    SessionNotFoundError,
    get_messages as fetch_messages,
    get_session_metrics as fetch_session_metrics,
    prepare_chat,
)
from app.services.chat.stream import stream_chat

router = APIRouter(prefix="/api/sessions", tags=["messages"])


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    session_id: int,
    db: AsyncSession = Depends(get_session),
):
    try:
        return await fetch_messages(db, session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/metrics", response_model=SessionMetricsResponse)
async def get_session_metrics(
    session_id: int,
    db: AsyncSession = Depends(get_session),
):
    try:
        return await fetch_session_metrics(db, session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/messages")
async def send_message(
    session_id: int,
    body: MessageCreate,
    db: AsyncSession = Depends(get_session),
):
    try:
        context = await prepare_chat(db, session_id, body.content)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return StreamingResponse(
        stream_chat(context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Trace-ID": context.trace_id,
        },
    )
