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
from app.prompts.registry import get_prompt_bundle
from app.services.llm import get_llm

logger = logging.getLogger(__name__)


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
    return {"reader_output": extract_last_content(result), "iterations": 1}


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
    return {"ideation_output": extract_last_content(result), "iterations": 1}


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
    return {"review_output": extract_last_content(result), "iterations": 1}


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
    return {"revision_output": str(result.content), "iterations": 1}


async def finalize_node(state: ResearchState, config: RunnableConfig) -> dict:
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
        config=invoke_config("Supervisor", "finalize", config, state),
    )
    return {"final_output": str(result.content), "iterations": 1}


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
