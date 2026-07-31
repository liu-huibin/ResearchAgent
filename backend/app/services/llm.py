import logging

from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_llm() -> ChatOpenAI:
    kwargs = {}
    if settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key
    logger.debug("Creating LLM: model=%s, base_url=%s", settings.llm_model_name, settings.llm_api_base)
    return ChatOpenAI(
        base_url=settings.llm_api_base,
        model=settings.llm_model_name,
        temperature=0.7,
        streaming=True,
        # Ask OpenAI-compatible providers to include usage in the final stream
        # chunk so Phase 5 can attribute tokens to individual agents.
        stream_usage=True,
        **kwargs,
    )
