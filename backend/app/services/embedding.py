import logging

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)
EMBEDDING_BATCH_SIZE = 10


def _get_client() -> OpenAI:
    kwargs = {}
    if settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key
    return OpenAI(
        base_url=settings.llm_api_base,
        **kwargs,
    )


def embed_documents(texts: list[str]) -> list[list[float]]:
    client = _get_client()
    all_embeddings = []
    logger.debug("Embedding %d texts with model=%s, batch_size=%d", len(texts), settings.embedding_model, EMBEDDING_BATCH_SIZE)
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]
        resp = client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
        )
        all_embeddings.extend(d.embedding for d in resp.data)
    logger.debug("Embedding complete: %d vectors generated", len(all_embeddings))
    return all_embeddings


def embed_query(text: str) -> list[float]:
    return embed_documents([text])[0]
