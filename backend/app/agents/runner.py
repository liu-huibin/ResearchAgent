"""Runtime event translation, limits, and metrics for the agent graph."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator

from langchain_core.runnables import RunnableConfig

from app.agents.graph import build_multi_agent_graph
from app.agents.progress import extract_citation_markers, sanitize_public_report
from app.agents.state import NODE_TO_AGENT
from app.core.config import settings
from app.prompts.registry import select_prompt_bundle
from app.services.observability import (
    create_workflow_callbacks,
    log_workflow_metrics,
    summarize_agent_usage,
)

logger = logging.getLogger(__name__)

_PUBLIC_REPORT_FIELD_BY_STAGE = {
    "reader": "reader_public_report",
    "ideation": "ideation_public_report",
    "reviewer": "reviewer_public_report",
    "revision": "revision_public_report",
}


async def run_multi_agent_workflow(
    user_message: str,
    document_text: str | None = None,
    session_id: int | None = None,
    trace_id: str | None = None,
) -> AsyncIterator[dict]:
    graph = build_multi_agent_graph()
    try:
        trace_uuid = uuid.UUID(trace_id) if trace_id else uuid.uuid4()
    except ValueError:
        trace_uuid = uuid.uuid4()
    trace_id = str(trace_uuid)
    prompts = select_prompt_bundle(session_id if session_id is not None else trace_id)
    usage_callback, callbacks, langsmith_enabled = create_workflow_callbacks()
    root_config: RunnableConfig = {
        "recursion_limit": settings.agent_max_iterations,
        "callbacks": callbacks,
        "run_id": trace_uuid,
        "run_name": "ResearchMate.MultiAgentWorkflow",
        "tags": ["researchmate", "multi-agent", prompts.variant],
        "metadata": {
            "session_id": session_id,
            "trace_id": trace_id,
            "prompt_variant": prompts.variant,
            "prompt_version": prompts.version,
        },
    }
    last_node = ""
    started_at = time.perf_counter()
    status = "completed"
    iterations = 0
    tool_calls = 0
    tool_failures = 0
    reported_stages: set[str] = set()
    final_streamed_parts: list[str] = []
    final_correction_emitted = False
    try:
        async with asyncio.timeout(settings.agent_timeout_seconds):
            async for event in graph.astream_events(
                {
                    "user_message": user_message,
                    "document_text": document_text or "",
                    "session_id": session_id or 0,
                    "trace_id": trace_id,
                    "prompt_variant": prompts.variant,
                    "prompt_version": prompts.version,
                    "iterations": 0,
                },
                config=root_config,
                version="v1",
            ):
                kind = event.get("event", "")
                metadata = event.get("metadata", {})
                node = metadata.get("research_stage") or metadata.get(
                    "langgraph_node", ""
                )
                agent_name = metadata.get("research_agent") or NODE_TO_AGENT.get(node)

                if node and node != last_node and agent_name:
                    last_node = node
                    iterations += 1
                    yield {"type": "agent", "agent": agent_name, "stage": node}

                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk is None:
                        continue
                    content = getattr(chunk, "content", "")
                    if content:
                        if node == "finalize":
                            final_streamed_parts.append(str(content))
                            yield {"type": "token", "content": content}
                        # Intermediate model output is internal reasoning. Keep
                        # it in memory only for partial-result recovery.
                elif kind == "on_chain_end":
                    report_field = _PUBLIC_REPORT_FIELD_BY_STAGE.get(node)
                    output = event.get("data", {}).get("output")
                    if (
                        node == "finalize"
                        and isinstance(output, dict)
                        and not final_correction_emitted
                    ):
                        final_output = str(output.get("final_output", ""))
                        streamed = "".join(final_streamed_parts)
                        if final_output and final_output.startswith(streamed):
                            correction = final_output[len(streamed):]
                            if correction:
                                yield {"type": "token", "content": correction}
                        elif final_output and not extract_citation_markers(streamed):
                            markers = extract_citation_markers(final_output)
                            if markers:
                                yield {
                                    "type": "token",
                                    "content": "\n\n可定位来源：" + " ".join(markers),
                                }
                        final_correction_emitted = True
                    report = ""
                    if report_field and isinstance(output, dict):
                        report = sanitize_public_report(
                            str(output.get(report_field, ""))
                        )
                    if report and node not in reported_stages:
                        reported_stages.add(node)
                        yield {
                            "type": "report",
                            "agent": agent_name or NODE_TO_AGENT[node],
                            "stage": node,
                            "content": report,
                        }
                elif kind == "on_tool_start":
                    tool_calls += 1
                    name = event.get("name", "unknown")
                    logger.info(
                        "Agent tool start: agent=%s tool=%s",
                        agent_name,
                        name,
                    )
                    yield {
                        "type": "action",
                        "agent": agent_name or "ReaderAgent",
                        "tool": name,
                    }
                elif kind == "on_tool_end":
                    name = event.get("name", "unknown")
                    output = str(event.get("data", {}).get("output", ""))
                    is_error = output.startswith(("读取文件失败:", "混合检索失败")) or "访问被拒绝" in output
                    if is_error:
                        tool_failures += 1
                    logger.info(
                        "Agent tool end: agent=%s tool=%s output_len=%d",
                        agent_name,
                        name,
                        len(output),
                    )
                    yield {
                        "type": "observation",
                        "agent": agent_name or "ReaderAgent",
                        "tool": name,
                        "is_error": is_error,
                    }
                elif kind == "on_tool_error":
                    tool_failures += 1
                    name = event.get("name", "unknown")
                    logger.warning(
                        "Agent tool error: agent=%s tool=%s",
                        agent_name,
                        name,
                    )
                    yield {
                        "type": "observation",
                        "agent": agent_name or "ReaderAgent",
                        "tool": name,
                        "is_error": True,
                    }
    except TimeoutError:
        status = "timeout"
        logger.warning(
            "Multi-agent workflow timed out after %d seconds",
            settings.agent_timeout_seconds,
        )
        yield {
            "type": "token",
            "content": "工作流已达到时间上限，请缩小问题范围后重试。",
        }
    except Exception as exc:
        logger.exception("Multi-agent workflow failed")
        error_name = type(exc).__name__.lower()
        if "recursion" in str(exc).lower() or "recursion" in error_name:
            status = "iteration_limit"
            yield {
                "type": "token",
                "content": "工作流已达到迭代上限，请缩小问题范围后重试。",
            }
        else:
            status = "error"
            yield {"type": "error", "content": "Agent 执行出错"}

    agent_usage = usage_callback.snapshot()
    totals = summarize_agent_usage(agent_usage)
    metrics = {
        "type": "metrics",
        "trace_id": trace_id,
        "session_id": session_id,
        "status": status,
        "prompt_variant": prompts.variant,
        "prompt_version": prompts.version,
        "langsmith_enabled": langsmith_enabled,
        "agent_usage": agent_usage,
        **totals,
        "iterations": iterations,
        "tool_calls": tool_calls,
        "tool_failures": tool_failures,
        "duration_ms": int((time.perf_counter() - started_at) * 1000),
    }
    log_workflow_metrics(metrics)
    yield metrics


async def run_reader_agent(
    user_message: str,
    document_text: str | None = None,
) -> AsyncIterator[dict]:
    """Backward-compatible alias retained for Phase 1-3 callers."""
    async for event in run_multi_agent_workflow(user_message, document_text):
        yield event
