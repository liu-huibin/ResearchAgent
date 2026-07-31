import logging
import os
import pickle

import jieba
from rank_bm25 import BM25Okapi

from app.core.config import settings

logger = logging.getLogger(__name__)

_INDEX_CACHE: dict[str, dict] = {}  # keyed by index name


def _tokenize(text: str) -> list[str]:
    return list(jieba.cut(text))


def _index_path(name: str) -> str:
    return os.path.join(settings.bm25_persist_dir, f"{name}.pkl")


def _get_or_load_index(name: str) -> tuple[BM25Okapi, list[dict], list[str]] | None:
    """Load BM25 index from cache or disk.

    Returns (bm25, metadatas, original_corpus) or None.
    """
    if name in _INDEX_CACHE:
        entry = _INDEX_CACHE[name]
        return entry["bm25"], entry["metadatas"], entry["corpus"]

    path = _index_path(name)
    if not os.path.exists(path):
        return None

    with open(path, "rb") as f:
        data = pickle.load(f)
    tokenized = data.get("tokenized_corpus", [])
    metadatas = data.get("metadatas", [])
    corpus = data.get("corpus", [])
    if not tokenized:
        return None
    bm25 = BM25Okapi(tokenized)
    _INDEX_CACHE[name] = {"bm25": bm25, "metadatas": metadatas, "corpus": corpus}
    return bm25, metadatas, corpus


def build_index(name: str, chunks: list[dict]) -> None:
    """Build a BM25 index from chunks and persist to disk.

    Each chunk is a dict with 'content' and 'metadata' keys.
    """
    if not chunks:
        # BM25Okapi cannot be constructed with an empty corpus. Treat an empty
        # rebuild as deletion so searches cannot use stale entries.
        delete_index(name)
        logger.info("BM25 index cleared: name=%s", name)
        return

    os.makedirs(settings.bm25_persist_dir, exist_ok=True)

    tokenized = [_tokenize(c["content"]) for c in chunks]
    bm25 = BM25Okapi(tokenized)
    metadatas = [c["metadata"] for c in chunks]
    corpus = [c["content"] for c in chunks]

    path = _index_path(name)
    with open(path, "wb") as f:
        pickle.dump({
            "tokenized_corpus": tokenized,
            "metadatas": metadatas,
            "corpus": corpus,
        }, f)

    _INDEX_CACHE[name] = {"bm25": bm25, "metadatas": metadatas, "corpus": corpus}
    logger.info("BM25 index built: name=%s, chunks=%d, path=%s", name, len(chunks), path)


def _persisted_index_count(name: str) -> int | None:
    """Return a validated persisted chunk count without constructing BM25."""
    cached = _INDEX_CACHE.get(name)
    if cached is not None:
        corpus = cached.get("corpus", [])
        metadatas = cached.get("metadatas", [])
        if len(corpus) == len(metadatas):
            return len(corpus)
        return None

    path = _index_path(name)
    if not os.path.exists(path):
        return None

    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
        tokenized = data.get("tokenized_corpus", [])
        metadatas = data.get("metadatas", [])
        corpus = data.get("corpus", [])
        if len(tokenized) == len(metadatas) == len(corpus):
            return len(corpus)
    except (OSError, pickle.PickleError, EOFError, AttributeError, TypeError):
        logger.warning("BM25 persisted index is unreadable: name=%s", name, exc_info=True)
    return None


def search_bm25(query: str, top_k: int = 20, name: str = "knowledge_base") -> list[dict]:
    """Search BM25 index and return top_k results with metadata and content."""
    entry = _get_or_load_index(name)
    if entry is None:
        logger.debug("BM25 search skipped: index '%s' not found", name)
        return []

    bm25, metadatas, corpus = entry
    tokenized_query = _tokenize(query)
    scores = bm25.get_scores(tokenized_query)

    if len(scores) == 0:
        return []

    indexed_scores = list(enumerate(scores))
    indexed_scores.sort(key=lambda x: x[1], reverse=True)
    top_indices = [idx for idx, _ in indexed_scores[:min(top_k, len(indexed_scores))]]

    results = []
    for idx in top_indices:
        meta = metadatas[idx]
        results.append({
            "id": f"doc_{meta['document_id']}_chunk_{meta['chunk_index']}",
            "content": corpus[idx] if idx < len(corpus) else "",
            "metadata": meta,
            "score": float(scores[idx]),
        })
    logger.debug("BM25 search: query=%s, returned=%d", query[:80], len(results))
    return results


def add_to_index(name: str, new_chunks: list[dict]) -> None:
    """Add new chunks to an existing BM25 index by rebuilding the full index."""
    entry = _get_or_load_index(name)
    existing_chunks = []
    if entry is not None:
        _, metadatas, corpus = entry
        for i, meta in enumerate(metadatas):
            existing_chunks.append({
                "content": corpus[i] if i < len(corpus) else "",
                "metadata": meta,
            })

    all_chunks = existing_chunks + new_chunks
    build_index(name, all_chunks)


def remove_from_index(name: str, doc_id: int) -> None:
    """Remove all chunks belonging to doc_id from the BM25 index."""
    entry = _get_or_load_index(name)
    if entry is None:
        return

    _, metadatas, corpus = entry
    remaining_chunks = []
    for i, meta in enumerate(metadatas):
        if meta.get("document_id") == doc_id:
            continue
        remaining_chunks.append({
            "content": corpus[i] if i < len(corpus) else "",
            "metadata": meta,
        })

    build_index(name, remaining_chunks)


def sync_from_chroma(collection_name: str = "knowledge_base") -> int:
    """Synchronize the BM25 index from the Chroma vector DB when needed.

    Useful for first-time Phase 3 deployment with existing knowledge base docs,
    or for recovery if the BM25 index becomes out of sync.

    Returns the number of chunks indexed.
    """
    from app.services.vectordb import get_collection

    coll = get_collection()
    chroma_count = coll.count()
    persisted_count = _persisted_index_count(collection_name)

    if chroma_count == 0:
        if persisted_count is not None:
            delete_index(collection_name)
            logger.info("BM25 index cleared because Chroma is empty")
        return 0

    if persisted_count == chroma_count:
        logger.info(
            "BM25 sync skipped: index already has %d chunks",
            chroma_count,
        )
        return chroma_count

    all_data = coll.get()
    if not all_data["ids"]:
        return 0

    chunks = []
    for i, chunk_id in enumerate(all_data["ids"]):
        content = all_data["documents"][i] if all_data["documents"] else ""
        metadata = all_data["metadatas"][i] if all_data["metadatas"] else {}
        if isinstance(metadata, dict):
            # Convert Chroma int metadata back (Chroma sometimes converts to int)
            meta = {
                "document_id": int(metadata.get("document_id", 0)),
                "filename": str(metadata.get("filename", "")),
                "chunk_index": int(metadata.get("chunk_index", 0)),
                "total_chunks": int(metadata.get("total_chunks", 0)),
            }
        else:
            continue
        chunks.append({"content": content, "metadata": meta})

    if chunks:
        build_index(collection_name, chunks)

    logger.info("BM25 sync from Chroma complete: %d chunks indexed", len(chunks))
    return len(chunks)


def delete_index(name: str) -> None:
    """Delete a BM25 index from disk and cache."""
    _INDEX_CACHE.pop(name, None)
    path = _index_path(name)
    if os.path.exists(path):
        os.remove(path)
