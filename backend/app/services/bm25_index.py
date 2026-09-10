import json
import logging
import os
import tempfile
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.core.file_permissions import harden_private_path

logger = logging.getLogger(__name__)

_INDEX_CACHE: dict[str, dict] = {}


def _tokenize(text: str) -> list[str]:
    return list(jieba.cut(text))


def _index_path(name: str) -> str:
    return os.path.join(settings.bm25_persist_dir, f"{name}.json")


def _validated_payload(data: object) -> tuple[list[list[str]], list[dict], list[str]]:
    if not isinstance(data, dict) or data.get("format_version") != 1:
        raise ValueError("unsupported BM25 index format")
    tokenized = data.get("tokenized_corpus")
    metadatas = data.get("metadatas")
    corpus = data.get("corpus")
    if not isinstance(tokenized, list) or not isinstance(metadatas, list) or not isinstance(corpus, list):
        raise ValueError("invalid BM25 index components")
    if not all(
        isinstance(tokens, list) and all(isinstance(token, str) for token in tokens)
        for tokens in tokenized
    ):
        raise ValueError("invalid BM25 token corpus")
    if not all(isinstance(metadata, dict) for metadata in metadatas):
        raise ValueError("invalid BM25 metadata")
    if not all(isinstance(content, str) for content in corpus):
        raise ValueError("invalid BM25 corpus")
    if not (len(tokenized) == len(metadatas) == len(corpus)):
        raise ValueError("inconsistent BM25 component counts")
    return tokenized, metadatas, corpus


def _read_payload(path: str) -> tuple[list[list[str]], list[dict], list[str]]:
    with open(path, "r", encoding="utf-8") as stream:
        return _validated_payload(json.load(stream))


def _get_or_load_index(name: str) -> tuple[BM25Okapi, list[dict], list[str]] | None:
    if name in _INDEX_CACHE:
        entry = _INDEX_CACHE[name]
        return entry["bm25"], entry["metadatas"], entry["corpus"]

    path = _index_path(name)
    if not os.path.exists(path):
        return None
    try:
        tokenized, metadatas, corpus = _read_payload(path)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        logger.warning("BM25 persisted index is unreadable: name=%s", name, exc_info=True)
        return None
    if not tokenized:
        return None
    bm25 = BM25Okapi(tokenized)
    _INDEX_CACHE[name] = {"bm25": bm25, "metadatas": metadatas, "corpus": corpus}
    return bm25, metadatas, corpus


def build_index(name: str, chunks: list[dict]) -> None:
    if not chunks:
        delete_index(name)
        logger.info("BM25 index cleared: name=%s", name)
        return

    os.makedirs(settings.bm25_persist_dir, exist_ok=True)
    if not harden_private_path(settings.bm25_persist_dir):
        raise PermissionError("could not restrict BM25 index directory permissions")
    tokenized = [_tokenize(c["content"]) for c in chunks]
    bm25 = BM25Okapi(tokenized)
    metadatas = [c["metadata"] for c in chunks]
    corpus = [c["content"] for c in chunks]
    payload = {
        "format_version": 1,
        "tokenized_corpus": tokenized,
        "metadatas": metadatas,
        "corpus": corpus,
    }

    path = _index_path(name)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{name}.", suffix=".tmp", dir=settings.bm25_persist_dir
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            Path(temporary).chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, path)
        if not harden_private_path(path):
            raise PermissionError("could not restrict BM25 index file permissions")
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise

    _INDEX_CACHE[name] = {"bm25": bm25, "metadatas": metadatas, "corpus": corpus}
    logger.info("BM25 index built: name=%s, chunks=%d, path=%s", name, len(chunks), path)


def _persisted_index_count(name: str) -> int | None:
    cached = _INDEX_CACHE.get(name)
    if cached is not None:
        corpus = cached.get("corpus", [])
        metadatas = cached.get("metadatas", [])
        return len(corpus) if len(corpus) == len(metadatas) else None

    path = _index_path(name)
    if not os.path.exists(path):
        return None
    try:
        _tokenized, _metadatas, corpus = _read_payload(path)
        return len(corpus)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        logger.warning("BM25 persisted index is unreadable: name=%s", name, exc_info=True)
        return None


def search_bm25(query: str, top_k: int = 20, name: str = "knowledge_base") -> list[dict]:
    entry = _get_or_load_index(name)
    if entry is None:
        logger.debug("BM25 search skipped: index '%s' not found", name)
        return []
    bm25, metadatas, corpus = entry
    scores = bm25.get_scores(_tokenize(query))
    if len(scores) == 0:
        return []
    indexed_scores = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    results = []
    for idx, _score in indexed_scores[: min(top_k, len(indexed_scores))]:
        meta = metadatas[idx]
        results.append(
            {
                "id": f"doc_{meta['document_id']}_chunk_{meta['chunk_index']}",
                "content": corpus[idx] if idx < len(corpus) else "",
                "metadata": meta,
                "score": float(scores[idx]),
            }
        )
    logger.debug("BM25 search returned=%d", len(results))
    return results


def add_to_index(name: str, new_chunks: list[dict]) -> None:
    entry = _get_or_load_index(name)
    existing_chunks = []
    if entry is not None:
        _, metadatas, corpus = entry
        existing_chunks = [
            {"content": corpus[i] if i < len(corpus) else "", "metadata": meta}
            for i, meta in enumerate(metadatas)
        ]
    build_index(name, existing_chunks + new_chunks)


def remove_from_index(name: str, doc_id: int) -> None:
    entry = _get_or_load_index(name)
    if entry is None:
        return
    _, metadatas, corpus = entry
    remaining_chunks = [
        {"content": corpus[i] if i < len(corpus) else "", "metadata": meta}
        for i, meta in enumerate(metadatas)
        if meta.get("document_id") != doc_id
    ]
    build_index(name, remaining_chunks)


def sync_from_chroma(collection_name: str = "knowledge_base") -> int:
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
        logger.info("BM25 sync skipped: index already has %d chunks", chroma_count)
        return chroma_count

    all_data = coll.get()
    if not all_data["ids"]:
        return 0
    chunks = []
    for i, _chunk_id in enumerate(all_data["ids"]):
        content = all_data["documents"][i] if all_data["documents"] else ""
        metadata = all_data["metadatas"][i] if all_data["metadatas"] else {}
        if not isinstance(metadata, dict):
            continue
        chunks.append(
            {
                "content": content,
                "metadata": {
                    "document_id": int(metadata.get("document_id", 0)),
                    "filename": str(metadata.get("filename", "")),
                    "chunk_index": int(metadata.get("chunk_index", 0)),
                    "total_chunks": int(metadata.get("total_chunks", 0)),
                },
            }
        )
    if chunks:
        build_index(collection_name, chunks)
    logger.info("BM25 sync from Chroma complete: %d chunks indexed", len(chunks))
    return len(chunks)


def delete_index(name: str) -> None:
    _INDEX_CACHE.pop(name, None)
    path = _index_path(name)
    if os.path.exists(path):
        os.remove(path)
