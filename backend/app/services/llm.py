from langchain_openai import ChatOpenAI

from app.config import settings


def get_llm() -> ChatOpenAI:
    kwargs = {}
    if settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key
    return ChatOpenAI(
        base_url=settings.llm_api_base,
        model=settings.llm_model_name,
        temperature=0.7,
        streaming=True,
        **kwargs,
    )
