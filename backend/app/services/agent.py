import asyncio
import logging
import time
import uuid
from functools import lru_cache
from typing import Annotated, AsyncIterator, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from app.config import settings
from app.prompts.registry import get_prompt_bundle, select_prompt_bundle
from app.services.llm import get_llm
from app.services.observability import (
    create_workflow_callbacks,
    log_workflow_metrics,
    summarize_agent_usage,
)
from app.tools.read_file import read_file
from app.tools.retrieve_knowledge import hybrid_retrieve

logger = logging.getLogger(__name__)

AgentName = Literal[
    "Supervisor",
    "ReaderAgent",
    "IdeationAgent",
    "ReviewerAgent",
]


class ResearchState(TypedDict, total=False):
    user_message: str
    document_text: str
    session_id: int
    trace_id: str
    prompt_variant: str
    prompt_version: str
    workflow: str
    reader_output: str
    ideation_output: str
    review_output: str
    revision_output: str
    final_output: str
    iterations: Annotated[int, lambda current, update: current + update]


_DEFAULT_PROMPTS = get_prompt_bundle("phase4-v1")
# Backward-compatible aliases retained for existing tests and integrations.
READER_SYSTEM_PROMPT = _DEFAULT_PROMPTS.reader
IDEATION_SYSTEM_PROMPT = _DEFAULT_PROMPTS.ideation
REVIEWER_SYSTEM_PROMPT = _DEFAULT_PROMPTS.reviewer
REVISION_SYSTEM_PROMPT = _DEFAULT_PROMPTS.revision
FINALIZER_SYSTEM_PROMPT = _DEFAULT_PROMPTS.finalizer


def classify_workflow(user_message: str) -> str:
    """Select the minimum workflow needed for the user's intent."""
    normalized = user_message.lower()
    ideation_terms = (
        "思路", "创新", "改进", "扩展", "方向", "方案", "idea",
        "improve", "innovation", "extension", "future work",
    )
    review_terms = (
        "审查", "评审", "核查", "验证", "批判", "review", "verify", "critique",
    )
    if any(term in normalized for term in ideation_terms):
        return "research_cycle"
    if any(term in normalized for term in review_terms):
        return "read_and_review"
    return "read_only"


def _extract_last_content(result: dict) -> str:
    for message in reversed(result.get("messages", [])):
        content = getattr(message, "content", "")
        if isinstance(content, str) and content.strip():
            return content
    return ""


def _invoke_config(
    agent: AgentName | None = None,
    stage: str | None = None,
    parent_config: RunnableConfig | None = None,
    state: ResearchState | None = None,
) -> RunnableConfig:
    config: RunnableConfig = {"recursion_limit": settings.agent_max_iterations}
    if parent_config:
        for key in ("callbacks", "tags"):
            if parent_config.get(key) is not None:
                config[key] = parent_config[key]
    metadata = dict((parent_config or {}).get("metadata") or {})
    if state:
        metadata.update(
            {
                "session_id": state.get("session_id"),
                "trace_id": state.get("trace_id"),
                "prompt_variant": state.get("prompt_variant"),
                "prompt_version": state.get("prompt_version"),
            }
        )
    if agent:
        metadata.update(
            {
                "research_agent": agent,
                "research_stage": stage or "",
            }
        )
        config["run_name"] = f"ResearchMate.{agent}.{stage or 'invoke'}"
    if metadata:
        config["metadata"] = metadata
    return config


@lru_cache(maxsize=2)
def _reader_agent(prompt_variant: str = "phase4-v1"):
    prompts = get_prompt_bundle(prompt_variant)
    return create_react_agent(
        model=get_llm(),
        tools=[hybrid_retrieve, read_file],
        state_modifier=prompts.reader,
    )


@lru_cache(maxsize=2)
def _ideation_agent(prompt_variant: str = "phase4-v1"):
    prompts = get_prompt_bundle(prompt_variant)
    return create_react_agent(
        model=get_llm(),
        tools=[hybrid_retrieve],
        state_modifier=prompts.ideation,
    )


@lru_cache(maxsize=2)
def _reviewer_agent(prompt_variant: str = "phase4-v1"):
    prompts = get_prompt_bundle(prompt_variant)
    return create_react_agent(
        model=get_llm(),
        tools=[hybrid_retrieve],
        state_modifier=prompts.reviewer,
    )


async def _supervisor_node(state: ResearchState) -> dict:
    workflow = classify_workflow(state["user_message"])
    logger.info("Supervisor selected workflow=%s", workflow)
    return {"workflow": workflow, "iterations": 1}


async def _reader_node(state: ResearchState, config: RunnableConfig) -> dict:
    document_context = state.get("document_text", "")
    if document_context:
        prompt = (
            f"用户任务：{state['user_message']}\n\n"
            f"当前会话论文正文：\n{document_context}"
        )
    else:
        prompt = (
            f"用户任务：{state['user_message']}\n\n"
            "当前会话没有可用论文正文。请检索知识库；若仍无证据，明确说明。"
        )
    result = await _reader_agent(state.get("prompt_variant", "phase4-v1")).ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config=_invoke_config("ReaderAgent", "reader", config, state),
    )
    return {"reader_output": _extract_last_content(result), "iterations": 1}


async def _ideation_node(state: ResearchState, config: RunnableConfig) -> dict:
    prompt = (
        f"用户任务：{state['user_message']}\n\n"
        f"ReaderAgent 分析：\n{state.get('reader_output', '')}"
    )
    result = await _ideation_agent(state.get("prompt_variant", "phase4-v1")).ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config=_invoke_config("IdeationAgent", "ideation", config, state),
    )
    return {"ideation_output": _extract_last_content(result), "iterations": 1}


async def _reviewer_node(state: ResearchState, config: RunnableConfig) -> dict:
    candidate = state.get("ideation_output") or state.get("reader_output", "")
    prompt = (
        f"用户任务：{state['user_message']}\n\n"
        f"ReaderAgent 分析：\n{state.get('reader_output', '')}\n\n"
        f"待审查内容：\n{candidate}"
    )
    result = await _reviewer_agent(state.get("prompt_variant", "phase4-v1")).ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config=_invoke_config("ReviewerAgent", "reviewer", config, state),
    )
    return {"review_output": _extract_last_content(result), "iterations": 1}


async def _revision_node(state: ResearchState, config: RunnableConfig) -> dict:
    prompt = (
        f"用户任务：{state['user_message']}\n\n"
        f"论文分析：\n{state.get('reader_output', '')}\n\n"
        f"原始思路：\n{state.get('ideation_output', '')}\n\n"
        f"审查意见：\n{state.get('review_output', '')}"
    )
    prompts = get_prompt_bundle(state.get("prompt_variant", "phase4-v1"))
    result = await get_llm().ainvoke(
        [SystemMessage(content=prompts.revision), HumanMessage(content=prompt)],
        config=_invoke_config("IdeationAgent", "revision", config, state),
    )
    return {"revision_output": str(result.content), "iterations": 1}


async def _finalize_node(state: ResearchState, config: RunnableConfig) -> dict:
    material = (
        f"用户任务：{state['user_message']}\n\n"
        f"ReaderAgent：\n{state.get('reader_output', '')}\n\n"
        f"IdeationAgent：\n{state.get('ideation_output', '')}\n\n"
        f"ReviewerAgent：\n{state.get('review_output', '')}\n\n"
        f"审查后修正版：\n{state.get('revision_output', '')}"
    )
    prompts = get_prompt_bundle(state.get("prompt_variant", "phase4-v1"))
    result = await get_llm().ainvoke(
        [SystemMessage(content=prompts.finalizer), HumanMessage(content=material)],
        config=_invoke_config("Supervisor", "finalize", config, state),
    )
    return {"final_output": str(result.content), "iterations": 1}


def _after_reader(state: ResearchState) -> str:
    if state["workflow"] == "research_cycle":
        return "ideation"
    if state["workflow"] == "read_and_review":
        return "reviewer"
    return "finalize"


def _after_review(state: ResearchState) -> str:
    review = state.get("review_output", "")
    needs_revision = state["workflow"] == "research_cycle" and (
        "审查结论：需修改" in review or "审查结论：不通过" in review
    )
    return "revision" if needs_revision else "finalize"


@lru_cache(maxsize=1)
def build_multi_agent_graph():
    """Build the multi-agent workflow used by the Phase 5 harness."""
    graph = StateGraph(ResearchState)
    graph.add_node("supervisor", _supervisor_node)
    graph.add_node("reader", _reader_node)
    graph.add_node("ideation", _ideation_node)
    graph.add_node("reviewer", _reviewer_node)
    graph.add_node("revision", _revision_node)
    graph.add_node("finalize", _finalize_node)
    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "reader")
    graph.add_conditional_edges(
        "reader",
        _after_reader,
        {"ideation": "ideation", "reviewer": "reviewer", "finalize": "finalize"},
    )
    graph.add_edge("ideation", "reviewer")
    graph.add_conditional_edges(
        "reviewer",
        _after_review,
        {"revision": "revision", "finalize": "finalize"},
    )
    graph.add_edge("revision", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


NODE_TO_AGENT: dict[str, AgentName] = {
    "supervisor": "Supervisor",
    "reader": "ReaderAgent",
    "ideation": "IdeationAgent",
    "reviewer": "ReviewerAgent",
    "revision": "IdeationAgent",
    "finalize": "Supervisor",
}


async def run_multi_agent_workflow(
    user_message: str,
    document_text: str | None = None,
    session_id: int | None = None,
    trace_id: str | None = None,
) -> AsyncIterator[dict]:
    """Run the graph with tracing, prompt assignment, and local metrics."""
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
                node = metadata.get("research_stage") or metadata.get("langgraph_node", "")
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
            "content": _format_partial_result(
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
                "content": f"工作流达到最大迭代次数 {settings.agent_max_iterations}，已强制结束。",
            }
            yield {
                "type": "token",
                "content": _format_partial_result(
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


def _format_partial_result(
    outputs: dict[AgentName, list[str]],
    reason: str,
) -> str:
    sections = [f"\n\n> {reason}"]
    for agent in ("ReaderAgent", "IdeationAgent", "ReviewerAgent"):
        content = "".join(outputs[agent]).strip()
        if content:
            sections.append(f"\n\n### {agent}\n\n{content}")
    return "".join(sections)
