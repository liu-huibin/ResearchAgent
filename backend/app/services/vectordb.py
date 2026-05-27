from typing import Optional

import chromadb
from chromadb.api import Collection

from app.config import settings

_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[Collection] = None


def _get_collection() -> Collection:
    global _client, _collection
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    if _collection is None:
        _collection = _client.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def index_document(chunks: list[dict], embeddings: list[list[float]]) -> None:
    collection = _get_collection()
    ids = []
    documents = []
    metadatas = []
    for chunk in chunks:
        doc_id = chunk["metadata"]["document_id"]
        chunk_idx = chunk["metadata"]["chunk_index"]
        ids.append(f"doc_{doc_id}_chunk_{chunk_idx}")
        documents.append(chunk["content"])
        metadatas.append(chunk["metadata"])

    collection.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)


def delete_document(doc_id: int) -> None:
    collection = _get_collection()
    try:
        results = collection.get(where={"document_id": doc_id})
        if results["ids"]:
            collection.delete(ids=results["ids"])
    except Exception:
        pass


def search(query_embedding: list[float], top_k: int = 5) -> list[dict]:
    collection = _get_collection()
    if collection.count() == 0:
        return []
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    formatted = []
    if results["ids"] and results["ids"][0]:
        for i, chunk_id in enumerate(results["ids"][0]):
            formatted.append({
                "id": chunk_id,
                "content": results["documents"][0][i] if results["documents"] else "",
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0.0,
            })
    return formatted
