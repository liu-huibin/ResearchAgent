"""Chat application service: queries, request preparation, and persistence."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.document import Document
from app.models.message import Message
from app.models.session import Session
from app.models.workflow_run import WorkflowRun
from app.schemas.metrics import SessionMetricsResponse
from app.services.file_parser import extract_text_from_file

logger = logging.getLogger(__name__)


class SessionNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class ChatContext:
    session_id: int
    user_message: str
    document_text: str | None
    trace_id: str
    started_at: datetime


@dataclass
class WorkflowResult:
    thought_parts: list[str] = field(default_factory=list)
    content_parts: list[str] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    metrics: dict | None = None
    stream_error: str = ""


async def get_messages(db: AsyncSession, session_id: int) -> list[Message]:
    await require_session(db, session_id)
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())


async def get_session_metrics(
    db: AsyncSession,
    session_id: int,
) -> SessionMetricsResponse:
    await require_session(db, session_id)
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.session_id == session_id)
        .order_by(WorkflowRun.completed_at.desc())
    )
    runs = list(result.scalars().all())
    return SessionMetricsResponse(
        session_id=session_id,
        input_tokens=sum(run.input_tokens for run in runs),
        output_tokens=sum(run.output_tokens for run in runs),
        total_tokens=sum(run.total_tokens for run in runs),
        run_count=len(runs),
        latest_run=runs[0] if runs else None,
        runs=runs[:20],
    )


async def prepare_chat(
    db: AsyncSession,
    session_id: int,
    user_message: str,
) -> ChatContext:
    session = await require_session(db, session_id)
    logger.info(
        "Message received: session_id=%d, content_len=%d",
        session_id,
        len(user_message),
    )

    db.add(Message(session_id=session_id, role="user", content=user_message))
    session.updated_at = datetime.now()
    db.add(session)
    await db.commit()

    document_text = None
    if session.active_document_id:
        document = await db.get(Document, session.active_document_id)
        if document:
            try:
                document_text = extract_text_from_file(document.file_path)
            except Exception:
                logger.warning(
                    "Failed to extract text for doc_id=%d",
                    session.active_document_id,
                    exc_info=True,
                )

    return ChatContext(
        session_id=session_id,
        user_message=user_message,
        document_text=document_text,
        trace_id=str(uuid.uuid4()),
        started_at=datetime.now(),
    )


async def persist_workflow_result(
    db: AsyncSession,
    context: ChatContext,
    result: WorkflowResult,
    status_override: str | None = None,
) -> Message:
    completed_at = datetime.now()
    metrics = dict(result.metrics or {})
    duration_ms = int(
        metrics.get(
            "duration_ms",
            (completed_at - context.started_at).total_seconds() * 1000,
        )
    )
    assistant_message = Message(
        session_id=context.session_id,
        role="assistant",
        content="".join(result.content_parts) or result.stream_error,
        thought="".join(result.thought_parts) if result.thought_parts else None,
        tool_calls=result.tool_calls or None,
    )
    db.add(assistant_message)
    await db.flush()
    workflow_run = WorkflowRun(
        session_id=context.session_id,
        assistant_message_id=assistant_message.id,
        trace_id=str(metrics.get("trace_id") or context.trace_id),
        status=status_override or str(metrics.get("status") or "completed"),
        prompt_variant=str(metrics.get("prompt_variant") or "phase4-v1"),
        prompt_version=str(metrics.get("prompt_version") or ""),
        langsmith_enabled=bool(metrics.get("langsmith_enabled", False)),
        input_tokens=int(metrics.get("input_tokens", 0) or 0),
        output_tokens=int(metrics.get("output_tokens", 0) or 0),
        total_tokens=int(metrics.get("total_tokens", 0) or 0),
        agent_usage=metrics.get("agent_usage") or None,
        iterations=int(metrics.get("iterations", 0) or 0),
        tool_calls=int(metrics.get("tool_calls", len(result.tool_calls)) or 0),
        tool_failures=int(metrics.get("tool_failures", 0) or 0),
        duration_ms=duration_ms,
        started_at=completed_at - timedelta(milliseconds=duration_ms),
        completed_at=completed_at,
    )
    db.add(workflow_run)
    await db.commit()
    await db.refresh(assistant_message)
    return assistant_message


async def require_session(db: AsyncSession, session_id: int) -> Session:
    session = await db.get(Session, session_id)
    if not session:
        raise SessionNotFoundError("会话不存在")
    return session
