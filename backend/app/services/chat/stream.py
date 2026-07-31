"""Translate workflow events into the existing ResearchMate SSE contract."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.core.database import async_session
from app.agents.runner import run_multi_agent_workflow
from app.services.chat.service import (
    ChatContext,
    WorkflowResult,
    persist_workflow_result,
)

logger = logging.getLogger(__name__)


def encode_sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


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

    async with session_factory() as stream_db:
        async def persist(status_override: str | None = None):
            nonlocal saved
            if saved:
                raise RuntimeError("工作流结果已持久化")
            message = await persist_workflow_result(
                stream_db,
                context,
                result,
                status_override,
            )
            saved = True
            return message

        try:
            async for event in workflow_runner(
                user_message=context.user_message,
                document_text=context.document_text,
                session_id=context.session_id,
                trace_id=context.trace_id,
            ):
                event_type = event.get("type", "")
                if event_type == "agent":
                    payload = {
                        "agent": event["agent"],
                        "stage": event.get("stage", ""),
                    }
                    result.thought_parts.append(f"\n[{event['agent']}]\n")
                    yield encode_sse("agent", payload)
                elif event_type == "thought":
                    result.thought_parts.append(event["content"])
                    yield encode_sse(
                        "thought",
                        {
                            "content": event["content"],
                            "agent": event.get("agent"),
                        },
                    )
                elif event_type == "action":
                    tool_call = {
                        "agent": event.get("agent"),
                        "tool": event["tool"],
                        "input": event["input"],
                    }
                    result.tool_calls.append(tool_call)
                    yield encode_sse("action", tool_call)
                elif event_type == "observation":
                    observation = {
                        "agent": event.get("agent"),
                        "tool": event["tool"],
                        "output": event["output"],
                        "is_error": bool(event.get("is_error", False)),
                    }
                    _attach_tool_observation(result.tool_calls, observation)
                    yield encode_sse("observation", observation)
                elif event_type == "token":
                    result.content_parts.append(event["content"])
                    yield encode_sse("token", {"content": event["content"]})
                elif event_type == "error":
                    result.stream_error = event.get("content", "Agent 执行出错")
                    logger.error(
                        "SSE error for session %d: %s",
                        context.session_id,
                        result.stream_error,
                    )
                    yield encode_sse("error", {"content": event["content"]})
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
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled for session %d", context.session_id)
            if not saved:
                result.stream_error = "对话已取消"
                await persist("cancelled")
            raise
        except Exception:
            logger.exception("SSE stream failed for session %d", context.session_id)
            result.stream_error = "对话流处理失败"
            if not saved:
                assistant_message = await persist("error")
                yield encode_sse("error", {"content": result.stream_error})
                yield encode_sse(
                    "done",
                    {
                        "message_id": assistant_message.id,
                        "trace_id": context.trace_id,
                    },
                )


def _attach_tool_observation(
    tool_calls: list[dict],
    observation: dict,
) -> None:
    for tool_call in reversed(tool_calls):
        if (
            tool_call["tool"] == observation["tool"]
            and tool_call.get("agent") == observation.get("agent")
            and "output" not in tool_call
        ):
            tool_call["output"] = observation["output"]
            tool_call["is_error"] = observation["is_error"]
            return
