"""Hybrid search orchestrator combining semantic search + BM25 + rerank."""
import logging

from app.config import settings
from app.services.vectordb import search as semantic_search
from app.services.bm25_index import search_bm25
from app.services.embedding import embed_query
from app.services.reranker import rerank

logger = logging.getLogger(__name__)


def hybrid_search(query: str, top_k: int | None = None) -> list[dict]:
    """Execute hybrid retrieval: semantic + BM25 → merge → rerank → top-K.

    Args:
        query: The search query.
        top_k: Final number of results (defaults to settings.hybrid_final_top_k).

    Returns:
        List of result dicts with keys: id, content, metadata, semantic_score,
        bm25_score, rerank_score.
    """
    if top_k is None:
        top_k = settings.hybrid_final_top_k
    semantic_k = settings.hybrid_semantic_top_k
    bm25_k = settings.hybrid_bm25_top_k

    # 1. Semantic search
    query_vec = embed_query(query)
    semantic_results = semantic_search(query_vec, top_k=semantic_k)
    logger.debug("Semantic search returned %d results for query=%s", len(semantic_results), query[:80])
    for r in semantic_results:
        r["semantic_score"] = r.pop("distance", 0.0)

    # 2. BM25 search
    bm25_results = search_bm25(query, top_k=bm25_k)
    logger.debug("BM25 search returned %d results for query=%s", len(bm25_results), query[:80])
    for r in bm25_results:
        r["bm25_score"] = r.get("score", 0.0)

    # 3. Merge and deduplicate by chunk ID
    merged: dict[str, dict] = {}
    for r in semantic_results:
        rid = r["id"]
        merged[rid] = r
        merged[rid].setdefault("bm25_score", 0.0)

    for r in bm25_results:
        rid = r["id"]
        if rid in merged:
            merged[rid]["bm25_score"] = r.get("bm25_score", 0.0)
        else:
            merged[rid] = r
            merged[rid].setdefault("semantic_score", 0.0)

    candidates = list(merged.values())

    logger.info("Hybrid search: query=%s, semantic=%d, bm25=%d, merged=%d", query[:80], len(semantic_results), len(bm25_results), len(candidates))

    if not candidates:
        logger.info("Hybrid search: no candidates for query=%s", query[:80])
        return []

    # 4. Rerank
    final = rerank(query, candidates, top_k=top_k)
    logger.info("Hybrid search final: %d results after rerank", len(final))
    return final
