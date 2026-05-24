import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.models.session import Session
from app.models.message import Message
from app.models.document import Document
from app.schemas.message import MessageCreate, MessageResponse
from app.services.agent import run_reader_agent
from app.services.file_parser import extract_text_from_file
from app.config import settings

router = APIRouter(prefix="/api/sessions", tags=["messages"])


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(session_id: int, db: AsyncSession = Depends(get_session)):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    return result.scalars().all()


@router.post("/{session_id}/messages")
async def send_message(
    session_id: int,
    body: MessageCreate,
    db: AsyncSession = Depends(get_session),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # Save user message
    user_msg = Message(session_id=session_id, role="user", content=body.content)
    db.add(user_msg)
    await db.commit()

    # Get document text if available
    doc_text = None
    if session.active_document_id:
        doc = await db.get(Document, session.active_document_id)
        if doc:
            try:
                doc_text = extract_text_from_file(doc.file_path)
            except Exception:
                doc_text = None

    async def generate_sse():
        thought_parts: list[str] = []
        content_parts: list[str] = []
        tool_calls_log: list[dict] = []

        try:
            async for event in run_reader_agent(
                user_message=body.content,
                document_text=doc_text,
            ):
                event_type = event.get("type", "")

                if event_type == "thought":
                    thought_parts.append(event["content"])
                    yield f"event: thought\ndata: {json.dumps({'content': event['content']}, ensure_ascii=False)}\n\n"

                elif event_type == "action":
                    tool_calls_log.append(event)
                    yield f"event: action\ndata: {json.dumps({'tool': event['tool'], 'input': event['input']}, ensure_ascii=False)}\n\n"

                elif event_type == "observation":
                    yield f"event: observation\ndata: {json.dumps({'tool': event['tool'], 'output': event['output']}, ensure_ascii=False)}\n\n"

                elif event_type == "token":
                    content_parts.append(event["content"])
                    yield f"event: token\ndata: {json.dumps({'content': event['content']}, ensure_ascii=False)}\n\n"

                elif event_type == "error":
                    yield f"event: error\ndata: {json.dumps({'content': event['content']}, ensure_ascii=False)}\n\n"
                    # Save partial response on error
                    assistant_msg = Message(
                        session_id=session_id,
                        role="assistant",
                        content="".join(content_parts) or event.get("content", ""),
                        thought="".join(thought_parts) or None,
                        tool_calls=tool_calls_log or None,
                    )
                    db.add(assistant_msg)
                    await db.commit()
                    yield f"event: done\ndata: {json.dumps({'message_id': assistant_msg.id}, ensure_ascii=False)}\n\n"
                    return

            # Save assistant message
            assistant_msg = Message(
                session_id=session_id,
                role="assistant",
                content="".join(content_parts),
                thought="".join(thought_parts) if thought_parts else None,
                tool_calls=tool_calls_log if tool_calls_log else None,
            )
            db.add(assistant_msg)
            await db.commit()
            await db.refresh(assistant_msg)

            yield f"event: done\ndata: {json.dumps({'message_id': assistant_msg.id}, ensure_ascii=False)}\n\n"

        except asyncio.CancelledError:
            # Client disconnected, save partial
            if content_parts:
                assistant_msg = Message(
                    session_id=session_id,
                    role="assistant",
                    content="".join(content_parts),
                    thought="".join(thought_parts) if thought_parts else None,
                    tool_calls=tool_calls_log if tool_calls_log else None,
                )
                db.add(assistant_msg)
                await db.commit()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
