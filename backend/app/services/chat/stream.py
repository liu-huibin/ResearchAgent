"""Translate workflow events into the existing ResearchMate SSE contract."""

import asyncio
import json
import logging
import time
import anyio
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.core.database import async_session
from app.agents.runner import run_multi_agent_workflow
from app.agents.progress import public_stage_detail, sanitize_public_report
from app.services.chat.service import (
    ChatContext,
    WorkflowResult,
    persist_workflow_result,
)

logger = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 5
CHECKPOINT_SECONDS = 5


def encode_sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _with_heartbeat(producer):
    pending = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(producer))
            ready, _ = await asyncio.wait({pending}, timeout=HEARTBEAT_SECONDS)
            if not ready:
                yield {"type": "heartbeat"}
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            yield event
    finally:
        if pending is not None:
            pending.cancel()
            with anyio.move_on_after(2, shield=True):
                try:
                    await pending
                except (asyncio.CancelledError, StopAsyncIteration):
                    pass


async def stream_chat(
    context: ChatContext,
    session_factory: Callable[[], Any] = async_session,
    workflow_runner: Callable[..., AsyncIterator[dict]] = run_multi_agent_workflow,
) -> AsyncIterator[str]:
    result = WorkflowResult()
    saved = False
    logger.info(
        "SSE stream started for session %d trace_id=%s",
        context.session_id,
        context.trace_id,
    )

    # Each attempt owns a fresh transaction. A commit whose acknowledgement was
    # lost is resolved by the unique trace_id, never by replaying the workflow.
    async def persist(status_override: str | None = None):
        nonlocal saved
        terminal_status = status_override or (result.metrics or {}).get("status")
        if result.stream_error:
            terminal_status = "error"
        if terminal_status and terminal_status != "running":
            _finish_running_stage(
                result.process_events,
                "succeeded" if terminal_status == "completed" else "failed",
            )
        for tool in result.tool_calls:
            if status_override != "running" and tool.get("status") == "running":
                tool.update(status="failed", is_error=True)
        for attempt in range(3):
            try:
                async with asyncio.timeout(3), session_factory() as db:
                    try:
                        message = await persist_workflow_result(db, context, result, status_override)
                    except BaseException:
                        await db.rollback()
                        raise
                saved = status_override != "running"
                return message
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.1 * (attempt + 1))

    producer = workflow_runner(
        user_message=context.user_message, document_text=context.document_text,
        session_id=context.session_id, trace_id=context.trace_id,
    )
    events = _with_heartbeat(producer)
    checkpoint_at = time.monotonic()
    previous_stage = ""
    try:
        try:
            yield encode_sse("start", {"trace_id": context.trace_id})
            async for event in events:
                if time.monotonic() - checkpoint_at >= CHECKPOINT_SECONDS:
                    await persist("running")
                    checkpoint_at = time.monotonic()
                event_type = event.get("type", "")
                if event_type == "heartbeat":
                    yield ": keepalive\n\n"
                elif event_type == "agent":
                    _finish_running_stage(result.process_events, "succeeded")
                    stage = event.get("stage", "")
                    detail = public_stage_detail(
                        stage,
                        context.user_message,
                        context.document_text,
                        previous_stage,
                    )
                    activity = {
                        "kind": "stage",
                        "agent": event["agent"],
                        "stage": stage,
                        "detail": detail,
                        "status": "running",
                    }
                    result.process_events.append(activity)
                    payload = {
                        "agent": event["agent"],
                        "stage": stage,
                        "detail": detail,
                    }
                    previous_stage = stage
                    yield encode_sse("agent", payload)
                elif event_type == "thought":
                    # Internal model reasoning is intentionally discarded.
                    continue
                elif event_type == "report":
                    report = sanitize_public_report(str(event.get("content", "")))
                    if not report:
                        continue
                    stage = str(event.get("stage", ""))
                    agent = event.get("agent")
                    _finish_stage_with_report(
                        result.process_events,
                        agent,
                        stage,
                        report,
                    )
                    yield encode_sse(
                        "report",
                        {
                            "agent": agent,
                            "stage": stage,
                            "content": report,
                        },
                    )
                elif event_type == "action":
                    tool_call = {
                        "kind": "tool",
                        "agent": event.get("agent"),
                        "tool": event["tool"],
                        "status": "running",
                    }
                    result.tool_calls.append(tool_call)
                    result.process_events.append(tool_call)
                    yield encode_sse("action", tool_call)
                elif event_type == "observation":
                    observation = {
                        "agent": event.get("agent"),
                        "tool": event["tool"],
                        "is_error": bool(event.get("is_error", False)),
                        "status": (
                            "failed" if event.get("is_error", False) else "succeeded"
                        ),
                    }
                    _attach_tool_observation(result.tool_calls, observation)
                    yield encode_sse("observation", observation)
                elif event_type == "token":
                    result.content_parts.append(event["content"])
                    yield encode_sse("token", {"content": event["content"]})
                elif event_type == "error":
                    result.stream_error = "Agent 执行出错"
                    logger.error(
                        "SSE error for session %d: %s",
                        context.session_id,
                        result.stream_error,
                    )
                    yield encode_sse("error", {"content": result.stream_error})
                elif event_type == "metrics":
                    result.metrics = event
                    payload = {
                        key: value for key, value in event.items() if key != "type"
                    }
                    yield encode_sse("metrics", payload)

            assistant_message = await persist()
            yield encode_sse(
                "done",
                {
                    "message_id": assistant_message.id,
                    "trace_id": context.trace_id,
                    "persisted": True,
                    "status": "error" if result.stream_error else (result.metrics or {}).get("status", "completed"),
                    "total_tokens": int(
                        (result.metrics or {}).get("total_tokens", 0) or 0
                    ),
                },
            )
            logger.info(
                "SSE stream completed for session %d, message_id=%d trace_id=%s",
                context.session_id,
                assistant_message.id,
                context.trace_id,
            )
        except (asyncio.CancelledError, GeneratorExit):
            logger.info("SSE stream cancelled for session %d", context.session_id)
            if not saved:
                result.stream_error = "对话已取消"
            raise
        except Exception:
            logger.exception("SSE stream failed for session %d", context.session_id)
            result.stream_error = "对话流处理失败"
            if not saved:
                try:
                    assistant_message = await persist("error")
                except Exception:
                    yield encode_sse("error", {"content": "回答保存失败，请保留当前内容；不要重复发送问题。", "trace_id": context.trace_id})
                    return
                yield encode_sse("error", {"content": result.stream_error})
                yield encode_sse(
                    "done",
                    {
                        "message_id": assistant_message.id,
                        "trace_id": context.trace_id,
                        "persisted": True,
                        "status": "error",
                    },
                )
    finally:
        # Starlette cancels the entire AnyIO scope on disconnect. Shield both
        # model cleanup and the final transaction, including generator aclose.
        with anyio.move_on_after(10, shield=True):
            try:
                await events.aclose()
                await producer.aclose()
            finally:
                if not saved:
                    result.stream_error = result.stream_error or "对话已取消"
                    try:
                        await persist("error" if result.stream_error == "对话流处理失败" else "cancelled")
                    except Exception:
                        logger.exception("Unable to save workflow trace_id=%s", context.trace_id)


def _attach_tool_observation(
    tool_calls: list[dict],
    observation: dict,
) -> None:
    for tool_call in reversed(tool_calls):
        if (
            tool_call["tool"] == observation["tool"]
            and tool_call.get("agent") == observation.get("agent")
            and tool_call.get("status") == "running"
        ):
            tool_call["status"] = observation["status"]
            tool_call["is_error"] = observation["is_error"]
            return


def _finish_running_stage(activities: list[dict], status: str) -> None:
    for activity in reversed(activities):
        if activity.get("kind") == "stage" and activity.get("status") == "running":
            activity["status"] = status
            return


def _finish_stage_with_report(
    activities: list[dict],
    agent: str | None,
    stage: str,
    report: str,
) -> None:
    for activity in reversed(activities):
        if (
            activity.get("kind") == "stage"
            and activity.get("agent") == agent
            and activity.get("stage") == stage
        ):
            activity["report"] = report
            activity["status"] = "succeeded"
            return
