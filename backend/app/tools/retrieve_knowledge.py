import logging

from langchain_core.tools import tool

from app.core.config import settings
logger = logging.getLogger(__name__)


@tool
def hybrid_retrieve(query: str, top_k: int = 5) -> str:
    """PRIMARY TOOL: Search the knowledge base using hybrid retrieval (semantic + BM25 + rerank).

    This is the DEFAULT tool for answering research questions. You MUST call this tool
    first before attempting to answer ANY question that involves academic/research content.

    Always search the knowledge base when the user:
    - Mentions any research topic, paper, study, method, experiment, or finding
    - Uses keywords: 搜索, 查找, 检索, 知识库, 文档, 论文, 研究, 有没有, 是否有
    - Asks "find", "search", "lookup", or "what do the documents say about..."
    - Asks any question that might be answered by uploaded documents

    Even if you think you know the answer, search the knowledge base first to provide
    accurate, sourced information from the user's uploaded documents.

    Args:
        query: A descriptive search query in Chinese or English. Make it specific.
        top_k: Number of results (1-10, default 5).

    Returns:
        Formatted hybrid retrieval results with source citations.
    """
    top_k = max(1, min(top_k, 10))
    logger.info("hybrid_retrieve called: query_len=%d, top_k=%d", len(query), top_k)
    try:
        # Lazy import keeps Agent graph startup independent from Chroma initialization.
        from app.services.hybrid_search import hybrid_search

        results = hybrid_search(query, top_k=top_k)
    except Exception:
        logger.exception("hybrid_retrieve failed")
        return "混合检索失败"

    logger.info("hybrid_retrieve results: %d chunks found", len(results))
    if not results:
        logger.warning("hybrid_retrieve returned no results")
        return f'知识库中未找到与"{query}"相关的内容。'

    parts = []
    for i, r in enumerate(results, 1):
        meta = r.get("metadata", {})
        doc_id = meta.get("document_id", "?")
        filename = meta.get("filename", "未知文件")
        chunk_idx = meta.get("chunk_index", "?")
        total = meta.get("total_chunks", "?")
        content = r.get("content", "")
        if len(content) > 1000:
            content = content[:1000] + "..."
        rerank_score = r.get("rerank_score", 0)

        parts.append(
            f"[来源 {i}] 文件: {filename}, 段落 {chunk_idx + 1}/{total}"
            f" (相关性: {rerank_score:.3f})\n"
            f"内容: {content}\n"
            f"[citation:doc_{doc_id}:chunk_{chunk_idx}]"
        )

    return "\n\n---\n\n".join(parts)
