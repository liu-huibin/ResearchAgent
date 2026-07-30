import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import async_session, get_session
from app.models.session import Session
from app.models.message import Message
from app.models.document import Document
from app.models.workflow_run import WorkflowRun
from app.schemas.message import MessageCreate, MessageResponse
from app.schemas.metrics import SessionMetricsResponse
from app.services.agent import run_multi_agent_workflow
from app.services.file_parser import extract_text_from_file

logger = logging.getLogger(__name__)
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


@router.get("/{session_id}/metrics", response_model=SessionMetricsResponse)
async def get_session_metrics(
    session_id: int,
    db: AsyncSession = Depends(get_session),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.session_id == session_id)
        .order_by(WorkflowRun.completed_at.desc())
    )
    all_runs = list(result.scalars().all())
    return SessionMetricsResponse(
        session_id=session_id,
        input_tokens=sum(run.input_tokens for run in all_runs),
        output_tokens=sum(run.output_tokens for run in all_runs),
        total_tokens=sum(run.total_tokens for run in all_runs),
        run_count=len(all_runs),
        latest_run=all_runs[0] if all_runs else None,
        runs=all_runs[:20],
    )


@router.post("/{session_id}/messages")
async def send_message(
    session_id: int,
    body: MessageCreate,
    db: AsyncSession = Depends(get_session),
):
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    logger.info("Message received: session_id=%d, content_len=%d", session_id, len(body.content))

    # Save user message
    user_msg = Message(session_id=session_id, role="user", content=body.content)
    db.add(user_msg)
    session.updated_at = datetime.now()
    db.add(session)
    await db.commit()

    # Get document text if available
    doc_text = None
    if session.active_document_id:
        doc = await db.get(Document, session.active_document_id)
        if doc:
            try:
                logger.info("Extracting document text for session %d: doc_id=%d", session_id, doc.id)
                doc_text = extract_text_from_file(doc.file_path)
            except Exception:
                logger.warning("Failed to extract text for doc_id=%d", session.active_document_id, exc_info=True)
                doc_text = None

    trace_id = str(uuid.uuid4())
    workflow_started_at = datetime.now()

    async def generate_sse():
        thought_parts: list[str] = []
        content_parts: list[str] = []
        tool_calls_log: list[dict] = []
        workflow_metrics: dict | None = None
        stream_error = ""
        saved = False
        logger.info(
            "SSE stream started for session %d trace_id=%s",
            session_id,
            trace_id,
        )

        async with async_session() as stream_db:
            async def persist_result(status_override: str | None = None) -> Message:
                nonlocal saved, workflow_metrics
                if saved:
                    raise RuntimeError("工作流结果已持久化")
                completed_at = datetime.now()
                metrics = dict(workflow_metrics or {})
                duration_ms = int(
                    metrics.get(
                        "duration_ms",
                        (completed_at - workflow_started_at).total_seconds() * 1000,
                    )
                )
                assistant_msg = Message(
                    session_id=session_id,
                    role="assistant",
                    content="".join(content_parts) or stream_error,
                    thought="".join(thought_parts) if thought_parts else None,
                    tool_calls=tool_calls_log if tool_calls_log else None,
                )
                stream_db.add(assistant_msg)
                await stream_db.flush()
                run = WorkflowRun(
                    session_id=session_id,
                    assistant_message_id=assistant_msg.id,
                    trace_id=str(metrics.get("trace_id") or trace_id),
                    status=status_override or str(metrics.get("status") or "completed"),
                    prompt_variant=str(metrics.get("prompt_variant") or "phase4-v1"),
                    prompt_version=str(metrics.get("prompt_version") or ""),
                    langsmith_enabled=bool(metrics.get("langsmith_enabled", False)),
                    input_tokens=int(metrics.get("input_tokens", 0) or 0),
                    output_tokens=int(metrics.get("output_tokens", 0) or 0),
                    total_tokens=int(metrics.get("total_tokens", 0) or 0),
                    agent_usage=metrics.get("agent_usage") or None,
                    iterations=int(metrics.get("iterations", 0) or 0),
                    tool_calls=int(metrics.get("tool_calls", len(tool_calls_log)) or 0),
                    tool_failures=int(metrics.get("tool_failures", 0) or 0),
                    duration_ms=duration_ms,
                    started_at=completed_at - timedelta(milliseconds=duration_ms),
                    completed_at=completed_at,
                )
                stream_db.add(run)
                await stream_db.commit()
                await stream_db.refresh(assistant_msg)
                saved = True
                return assistant_msg

            try:
                async for event in run_multi_agent_workflow(
                    user_message=body.content,
                    document_text=doc_text,
                    session_id=session_id,
                    trace_id=trace_id,
                ):
                    event_type = event.get("type", "")

                    if event_type == "agent":
                        payload = {
                            "agent": event["agent"],
                            "stage": event.get("stage", ""),
                        }
                        thought_parts.append(f"\n[{event['agent']}]\n")
                        yield f"event: agent\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

                    elif event_type == "thought":
                        thought_parts.append(event["content"])
                        payload = {
                            "content": event["content"],
                            "agent": event.get("agent"),
                        }
                        yield f"event: thought\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

                    elif event_type == "action":
                        tool_call = {
                            "agent": event.get("agent"),
                            "tool": event["tool"],
                            "input": event["input"],
                        }
                        tool_calls_log.append(tool_call)
                        yield f"event: action\ndata: {json.dumps(tool_call, ensure_ascii=False)}\n\n"

                    elif event_type == "observation":
                        observation = {
                            "agent": event.get("agent"),
                            "tool": event["tool"],
                            "output": event["output"],
                            "is_error": bool(event.get("is_error", False)),
                        }
                        for tool_call in reversed(tool_calls_log):
                            if (
                                tool_call["tool"] == event["tool"]
                                and tool_call.get("agent") == event.get("agent")
                                and "output" not in tool_call
                            ):
                                tool_call["output"] = event["output"]
                                tool_call["is_error"] = observation["is_error"]
                                break
                        yield f"event: observation\ndata: {json.dumps(observation, ensure_ascii=False)}\n\n"

                    elif event_type == "token":
                        content_parts.append(event["content"])
                        yield f"event: token\ndata: {json.dumps({'content': event['content']}, ensure_ascii=False)}\n\n"

                    elif event_type == "error":
                        stream_error = event.get("content", "Agent 执行出错")
                        logger.error("SSE error for session %d: %s", session_id, event.get("content", ""))
                        yield f"event: error\ndata: {json.dumps({'content': event['content']}, ensure_ascii=False)}\n\n"

                    elif event_type == "metrics":
                        workflow_metrics = event
                        payload = {key: value for key, value in event.items() if key != "type"}
                        yield f"event: metrics\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

                assistant_msg = await persist_result()
                done_payload = {
                    "message_id": assistant_msg.id,
                    "trace_id": trace_id,
                    "total_tokens": int((workflow_metrics or {}).get("total_tokens", 0) or 0),
                }
                yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                logger.info(
                    "SSE stream completed for session %d, message_id=%d trace_id=%s",
                    session_id,
                    assistant_msg.id,
                    trace_id,
                )

            except asyncio.CancelledError:
                logger.info("SSE stream cancelled for session %d", session_id)
                if not saved:
                    stream_error = "对话已取消"
                    await persist_result("cancelled")
                raise
            except Exception as exc:
                logger.exception("SSE stream failed for session %d", session_id)
                stream_error = "对话流处理失败"
                if not saved:
                    try:
                        assistant_msg = await persist_result("error")
                    except Exception:
                        logger.exception("Failed to persist errored workflow")
                        raise exc
                    yield f"event: error\ndata: {json.dumps({'content': stream_error}, ensure_ascii=False)}\n\n"
                    yield f"event: done\ndata: {json.dumps({'message_id': assistant_msg.id, 'trace_id': trace_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
