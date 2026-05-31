"""Reranker service for hybrid retrieval.

Uses embedding cosine similarity as the default rerank strategy.
If rerank_model is configured, uses that cross-encoder model instead.
"""

from app.config import settings
from app.services.embedding import embed_query, embed_documents


def rerank(query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
    """Rerank candidate chunks using embedding cosine similarity.

    Args:
        query: The search query.
        candidates: List of dicts with 'content' and 'id' keys.
        top_k: Number of top results to return.

    Returns:
        Reranked candidates with 'rerank_score' added, sorted by relevance.
    """
    if not candidates:
        return []

    if settings.rerank_model:
        return _cross_encoder_rerank(query, candidates, top_k)

    return _embedding_rerank(query, candidates, top_k)


def _embedding_rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """Rerank using query-document embedding cosine similarity."""
    import math

    query_vec = embed_query(query)
    texts = [c["content"] for c in candidates]
    doc_vecs = embed_documents(texts)

    for i, doc_vec in enumerate(doc_vecs):
        similarity = _cosine_similarity(query_vec, doc_vec)
        candidates[i]["rerank_score"] = similarity

    candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    return candidates[:top_k]


def _cross_encoder_rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """Rerank using a cross-encoder model (e.g., bge-reranker-v2-m3)."""
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(settings.rerank_model)
    pairs = [[query, c["content"]] for c in candidates]
    scores = model.predict(pairs, show_progress_bar=False)

    for i, score in enumerate(scores):
        candidates[i]["rerank_score"] = float(score)

    candidates.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    return candidates[:top_k]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
