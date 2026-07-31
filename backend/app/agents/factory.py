"""Agent factories and invocation metadata helpers."""

from functools import lru_cache

from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from app.agents.state import AgentName, ResearchState
from app.core.config import settings
from app.prompts.registry import get_prompt_bundle
from app.services.llm import get_llm
from app.tools.read_file import read_file
from app.tools.retrieve_knowledge import hybrid_retrieve

_DEFAULT_PROMPTS = get_prompt_bundle("phase4-v1")
READER_SYSTEM_PROMPT = _DEFAULT_PROMPTS.reader
IDEATION_SYSTEM_PROMPT = _DEFAULT_PROMPTS.ideation
REVIEWER_SYSTEM_PROMPT = _DEFAULT_PROMPTS.reviewer
REVISION_SYSTEM_PROMPT = _DEFAULT_PROMPTS.revision
FINALIZER_SYSTEM_PROMPT = _DEFAULT_PROMPTS.finalizer


def extract_last_content(result: dict) -> str:
    for message in reversed(result.get("messages", [])):
        content = getattr(message, "content", "")
        if isinstance(content, str) and content.strip():
            return content
    return ""


def invoke_config(
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
