from langchain_core.tools import tool

from app.config import settings
from app.services.embedding import embed_query
from app.services.vectordb import search


@tool
def retrieve_knowledge(query: str, top_k: int = 5) -> str:
    """Search the knowledge base for documents related to the query.

    Use this tool when the user asks about content that might be in the
    knowledge base, or when they reference specific uploaded documents.
    This tool performs semantic search using vector embeddings.

    Args:
        query: A natural language search query describing what to find.
        top_k: Number of results to return (1-10, default 5).

    Returns:
        Formatted retrieval results with source citations.
    """
    top_k = max(1, min(top_k, 10))
    try:
        query_vec = embed_query(query)
    except Exception as e:
        return f"嵌入查询失败: {str(e)}"

    try:
        results = search(query_vec, top_k=top_k)
    except Exception as e:
        return f"检索失败: {str(e)}"

    if not results:
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

        parts.append(
            f"[来源 {i}] 文件: {filename}, 段落 {chunk_idx + 1}/{total}\n"
            f"内容: {content}\n"
            f"[citation:doc_{doc_id}:chunk_{chunk_idx}]"
        )

    return "\n\n---\n\n".join(parts)
