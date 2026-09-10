"""LangGraph node behavior and workflow routing decisions."""

import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agents.factory import (
    _ideation_agent,
    _reader_agent,
    _reviewer_agent,
    extract_last_content,
    invoke_config,
)
from app.agents.state import ResearchState
from app.agents.progress import (
    classify_workflow,
    ensure_citation_fallback,
    extract_citation_markers,
    split_agent_output,
)
from app.prompts.registry import get_prompt_bundle
from app.services.llm import get_llm

logger = logging.getLogger(__name__)


def _result_citations(result: dict) -> list[str]:
    messages = result.get("messages", []) if isinstance(result, dict) else []
    return extract_citation_markers(
        *(getattr(message, "content", "") for message in messages)
    )


async def supervisor_node(state: ResearchState) -> dict:
    workflow = classify_workflow(state["user_message"])
    logger.info("Supervisor selected workflow=%s", workflow)
    return {"workflow": workflow, "iterations": 1}


async def reader_node(state: ResearchState, config: RunnableConfig) -> dict:
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
        config=invoke_config("ReaderAgent", "reader", config, state),
    )
    output, report = split_agent_output(extract_last_content(result))
    return {
        "reader_output": output,
        "reader_public_report": report,
        "citation_markers": _result_citations(result),
        "iterations": 1,
    }


async def ideation_node(state: ResearchState, config: RunnableConfig) -> dict:
    prompt = (
        f"用户任务：{state['user_message']}\n\n"
        f"ReaderAgent 分析：\n{state.get('reader_output', '')}"
    )
    result = await _ideation_agent(
        state.get("prompt_variant", "phase4-v1")
    ).ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config=invoke_config("IdeationAgent", "ideation", config, state),
    )
    output, report = split_agent_output(extract_last_content(result))
    return {
        "ideation_output": output,
        "ideation_public_report": report,
        "citation_markers": _result_citations(result),
        "iterations": 1,
    }


async def reviewer_node(state: ResearchState, config: RunnableConfig) -> dict:
    candidate = state.get("ideation_output") or state.get("reader_output", "")
    prompt = (
        f"用户任务：{state['user_message']}\n\n"
        f"ReaderAgent 分析：\n{state.get('reader_output', '')}\n\n"
        f"待审查内容：\n{candidate}"
    )
    result = await _reviewer_agent(
        state.get("prompt_variant", "phase4-v1")
    ).ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config=invoke_config("ReviewerAgent", "reviewer", config, state),
    )
    output, report = split_agent_output(extract_last_content(result))
    return {
        "review_output": output,
        "reviewer_public_report": report,
        "citation_markers": _result_citations(result),
        "iterations": 1,
    }


async def revision_node(state: ResearchState, config: RunnableConfig) -> dict:
    prompt = (
        f"用户任务：{state['user_message']}\n\n"
        f"论文分析：\n{state.get('reader_output', '')}\n\n"
        f"原始思路：\n{state.get('ideation_output', '')}\n\n"
        f"审查意见：\n{state.get('review_output', '')}"
    )
    prompts = get_prompt_bundle(state.get("prompt_variant", "phase4-v1"))
    result = await get_llm().ainvoke(
        [SystemMessage(content=prompts.revision), HumanMessage(content=prompt)],
        config=invoke_config("IdeationAgent", "revision", config, state),
    )
    output, report = split_agent_output(str(result.content))
    return {
        "revision_output": output,
        "revision_public_report": report,
        "citation_markers": extract_citation_markers(result.content),
        "iterations": 1,
    }


async def finalize_node(state: ResearchState, config: RunnableConfig) -> dict:
    citations = extract_citation_markers(
        *state.get("citation_markers", []),
        state.get("reader_output", ""),
        state.get("ideation_output", ""),
        state.get("review_output", ""),
        state.get("revision_output", ""),
    )
    material = (
        f"用户任务：{state['user_message']}\n\n"
        f"ReaderAgent：\n{state.get('reader_output', '')}\n\n"
        f"IdeationAgent：\n{state.get('ideation_output', '')}\n\n"
        f"ReviewerAgent：\n{state.get('review_output', '')}\n\n"
        f"审查后修正版：\n{state.get('revision_output', '')}"
    )
    if citations:
        material += (
            "\n\n可用的机器定位标记（引用相关事实时必须原样复制，不得改写为"
            "章节号、文献序号或“来源 N”）：\n"
            + " ".join(citations)
        )
    prompts = get_prompt_bundle(state.get("prompt_variant", "phase4-v1"))
    result = await get_llm().ainvoke(
        [SystemMessage(content=prompts.finalizer), HumanMessage(content=material)],
        config=invoke_config("Supervisor", "finalize", config, state),
    )
    return {
        "final_output": ensure_citation_fallback(str(result.content), citations),
        "iterations": 1,
    }


def after_reader(state: ResearchState) -> str:
    if state["workflow"] == "research_cycle":
        return "ideation"
    if state["workflow"] == "read_and_review":
        return "reviewer"
    return "finalize"


def after_review(state: ResearchState) -> str:
    review = state.get("review_output", "")
    needs_revision = state["workflow"] == "research_cycle" and (
        "审查结论：需修改" in review or "审查结论：不通过" in review
    )
    return "revision" if needs_revision else "finalize"
