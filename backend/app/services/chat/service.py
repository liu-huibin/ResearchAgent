"""Chat application service: queries, request preparation, and persistence."""

import asyncio
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
from app.core.config import settings
from app.schemas.metrics import SessionMetricsResponse
from app.services.chunking import chunk_document
from app.services.file_parser import extract_text_from_file
from app.services.sessions.titles import generate_session_title, is_placeholder_title

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
    content_parts: list[str] = field(default_factory=list)
    process_events: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    metrics: dict | None = None
    stream_error: str = ""


def format_citable_document_context(document: Document, text: str) -> str:
    """Attach stable machine citations to an active session document."""
    if not text.strip() or document.id is None:
        return text
    chunks = chunk_document(text, document.filename, document.id)
    return "\n\n".join(
        f"{chunk['content']}\n"
        f"[citation:doc_{document.id}:chunk_{chunk['metadata']['chunk_index']}]"
        for chunk in chunks
    )


async def get_messages(db: AsyncSession, session_id: int) -> list[Message]:
    await require_session(db, session_id)
    await recover_stale_runs(db, session_id)
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at, Message.id)
    )
    return list(result.scalars().all())


async def get_session_metrics(
    db: AsyncSession,
    session_id: int,
) -> SessionMetricsResponse:
    await require_session(db, session_id)
    await recover_stale_runs(db, session_id)
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


async def recover_stale_runs(db: AsyncSession, session_id: int) -> None:
    """After the hard workflow deadline plus cleanup grace, a running record
    is an interrupted process, not a completed answer. Never replay its input."""
    cutoff = datetime.now() - timedelta(seconds=settings.agent_timeout_seconds + 60)
    runs = (await db.execute(select(WorkflowRun).where(
        WorkflowRun.session_id == session_id, WorkflowRun.status == "running",
        WorkflowRun.started_at < cutoff,
    ).with_for_update())).scalars().all()
    for run in runs:
        run.status = "interrupted"
        run.completed_at = datetime.now()
        message = await db.get(Message, run.assistant_message_id) if run.assistant_message_id else None
        if message:
            if not message.content:
                message.content = "工作流异常中断，未生成可恢复的回答。"
            message.tool_calls = [dict(tool, status="failed", is_error=True)
                                  if tool.get("status") == "running" else tool
                                  for tool in (message.tool_calls or [])]
        else:
            message = Message(session_id=session_id, role="assistant",
                              content="工作流异常中断，未生成可恢复的回答。")
            db.add(message)
            await db.flush()
            run.assistant_message_id = message.id
        db.add(run)
    if runs:
        await db.commit()


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
    if is_placeholder_title(session.title):
        session.title = generate_session_title(user_message)
    session.updated_at = datetime.now()
    db.add(session)
    trace_id = str(uuid.uuid4())
    started_at = datetime.now()
    db.add(WorkflowRun(session_id=session_id, trace_id=trace_id,
                       status="running", started_at=started_at,
                       completed_at=started_at))
    # Make the user's input and durable run identity visible before document
    # parsing or model execution can fail.
    await db.commit()

    document_text = None
    if session.active_document_id:
        document = await db.get(Document, session.active_document_id)
        if document:
            try:
                extracted = await asyncio.to_thread(
                    extract_text_from_file,
                    document.file_path,
                )
                document_text = format_citable_document_context(document, extracted)
            except Exception:
                logger.warning(
                    "Failed to extract text for doc_id=%d",
                    session.active_document_id,
                    exc_info=True,
                )

    context = ChatContext(
        session_id=session_id,
        user_message=user_message,
        document_text=document_text,
        trace_id=trace_id,
        started_at=started_at,
    )
    return context


async def persist_workflow_result(
    db: AsyncSession,
    context: ChatContext,
    result: WorkflowResult,
    status_override: str | None = None,
) -> Message:
    existing = (await db.execute(
        select(WorkflowRun).where(WorkflowRun.trace_id == context.trace_id).with_for_update()
    )).scalar_one_or_none()
    previous_message = None
    if existing and existing.assistant_message_id:
        message = await db.get(Message, existing.assistant_message_id)
        if message is None:
            raise RuntimeError("工作流消息缺失")
        if existing.status != "running":
            return message
        previous_message = message
    completed_at = datetime.now()
    metrics = dict(result.metrics or {})
    duration_ms = int(
        metrics.get(
            "duration_ms",
            (completed_at - context.started_at).total_seconds() * 1000,
        )
    )
    assistant_message = Message(
        id=previous_message.id if previous_message else None,
        session_id=context.session_id,
        role="assistant",
        content="".join(result.content_parts) or result.stream_error,
        # Never persist chain-of-thought or raw tool payloads. tool_calls holds
        # only the execution status summaries produced by stream_chat.
        thought=None,
        tool_calls=(result.process_events or result.tool_calls) or None,
    )
    if previous_message:
        previous_message.content = assistant_message.content
        previous_message.tool_calls = assistant_message.tool_calls
        assistant_message = previous_message
    db.add(assistant_message)
    await db.flush()
    workflow_run = WorkflowRun(
        session_id=context.session_id,
        assistant_message_id=assistant_message.id,
        trace_id=context.trace_id,
        status=status_override or ("error" if result.stream_error else str(metrics.get("status") or "completed")),
        prompt_variant=str(metrics.get("prompt_variant") or "phase4-v1"),
        prompt_version=str(metrics.get("prompt_version") or ""),
        langsmith_enabled=bool(metrics.get("langsmith_enabled", False)),
        input_tokens=int(metrics.get("input_tokens", 0) or 0),
        output_tokens=int(metrics.get("output_tokens", 0) or 0),
        total_tokens=int(metrics.get("total_tokens", 0) or 0),
        agent_usage=metrics.get("agent_usage") or None,
        iterations=int(metrics.get("iterations", 0) or 0),
        tool_calls=int(metrics.get("tool_calls", len(result.tool_calls)) or 0),
        tool_failures=max(int(metrics.get("tool_failures", 0) or 0),
                          sum(tool.get("status") == "failed" for tool in result.tool_calls)),
        duration_ms=duration_ms,
        started_at=context.started_at,
        completed_at=completed_at,
    )
    if existing:
        for key, value in workflow_run.model_dump(exclude={"id"}).items():
            setattr(existing, key, value)
        db.add(existing)
    else:
        db.add(workflow_run)
    await db.commit()
    return assistant_message


async def require_session(db: AsyncSession, session_id: int) -> Session:
    session = await db.get(Session, session_id)
    if not session:
        raise SessionNotFoundError("会话不存在")
    return session
