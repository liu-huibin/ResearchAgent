"""Runtime event translation, limits, and metrics for the agent graph."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator

from langchain_core.runnables import RunnableConfig

from app.agents.graph import build_multi_agent_graph
from app.agents.state import AgentName, NODE_TO_AGENT
from app.core.config import settings
from app.prompts.registry import select_prompt_bundle
from app.services.observability import (
    create_workflow_callbacks,
    log_workflow_metrics,
    summarize_agent_usage,
)

logger = logging.getLogger(__name__)


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
    partial_outputs: dict[AgentName, list[str]] = {
        "Supervisor": [],
        "ReaderAgent": [],
        "IdeationAgent": [],
        "ReviewerAgent": [],
    }
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
                        if agent_name:
                            partial_outputs[agent_name].append(content)
                        if node == "finalize":
                            yield {"type": "token", "content": content}
                        elif agent_name:
                            yield {
                                "type": "thought",
                                "content": content,
                                "agent": agent_name,
                            }
                elif kind == "on_tool_start":
                    tool_calls += 1
                    name = event.get("name", "unknown")
                    input_data = event.get("data", {}).get("input", {})
                    logger.info(
                        "Agent tool start: agent=%s tool=%s input=%s",
                        agent_name,
                        name,
                        str(input_data)[:200],
                    )
                    yield {
                        "type": "action",
                        "agent": agent_name or "ReaderAgent",
                        "tool": name,
                        "input": input_data,
                    }
                elif kind == "on_tool_end":
                    name = event.get("name", "unknown")
                    output = str(event.get("data", {}).get("output", ""))
                    is_error = output.startswith("读取文件失败:") or "访问被拒绝" in output
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
                        "output": output[:500] + ("..." if len(output) > 500 else ""),
                        "is_error": is_error,
                    }
                elif kind == "on_tool_error":
                    tool_failures += 1
                    name = event.get("name", "unknown")
                    error = str(event.get("data", {}).get("error", "工具调用失败"))
                    logger.warning(
                        "Agent tool error: agent=%s tool=%s error=%s",
                        agent_name,
                        name,
                        error[:300],
                    )
                    yield {
                        "type": "observation",
                        "agent": agent_name or "ReaderAgent",
                        "tool": name,
                        "output": error[:500],
                        "is_error": True,
                    }
    except TimeoutError:
        status = "timeout"
        logger.warning(
            "Multi-agent workflow timed out after %d seconds",
            settings.agent_timeout_seconds,
        )
        yield {
            "type": "thought",
            "agent": "Supervisor",
            "content": "工作流达到超时上限，正在返回已生成的部分结果。",
        }
        yield {
            "type": "token",
            "content": format_partial_result(
                partial_outputs,
                "工作流已达到时间上限，以下为当前可用的阶段性结果。",
            ),
        }
    except Exception as exc:
        logger.exception("Multi-agent workflow failed")
        error_name = type(exc).__name__.lower()
        if "recursion" in str(exc).lower() or "recursion" in error_name:
            status = "iteration_limit"
            yield {
                "type": "thought",
                "agent": "Supervisor",
                "content": (
                    f"工作流达到最大迭代次数 {settings.agent_max_iterations}，"
                    "已强制结束。"
                ),
            }
            yield {
                "type": "token",
                "content": format_partial_result(
                    partial_outputs,
                    "工作流已达到迭代上限，以下为当前可用的阶段性结果。",
                ),
            }
        else:
            status = "error"
            yield {"type": "error", "content": f"Agent 执行出错: {exc}"}

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


def format_partial_result(
    outputs: dict[AgentName, list[str]],
    reason: str,
) -> str:
    sections = [f"\n\n> {reason}"]
    for agent in ("ReaderAgent", "IdeationAgent", "ReviewerAgent"):
        content = "".join(outputs[agent]).strip()
        if content:
            sections.append(f"\n\n### {agent}\n\n{content}")
    return "".join(sections)
