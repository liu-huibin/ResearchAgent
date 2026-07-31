import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.services import bm25_index


def _chunk(document_id: int, chunk_index: int) -> dict:
    return {
        "content": f"content-{document_id}-{chunk_index}",
        "metadata": {
            "document_id": document_id,
            "filename": "paper.txt",
            "chunk_index": chunk_index,
            "total_chunks": 2,
        },
    }


class FakeCollection:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.get_calls = 0

    def count(self):
        return len(self.chunks)

    def get(self):
        self.get_calls += 1
        return {
            "ids": [
                f"doc_{item['metadata']['document_id']}_chunk_{item['metadata']['chunk_index']}"
                for item in self.chunks
            ],
            "documents": [item["content"] for item in self.chunks],
            "metadatas": [item["metadata"] for item in self.chunks],
        }


class BM25SyncTests(unittest.TestCase):
    def setUp(self):
        bm25_index._INDEX_CACHE.clear()

    def tearDown(self):
        bm25_index._INDEX_CACHE.clear()

    def test_matching_persisted_count_skips_chroma_read_and_rebuild(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            collection = FakeCollection([_chunk(1, 0), _chunk(1, 1)])
            with patch.object(settings, "bm25_persist_dir", temp_dir):
                bm25_index.build_index("knowledge_base", collection.chunks)
                bm25_index._INDEX_CACHE.clear()
                with patch(
                    "app.services.vectordb.get_collection",
                    return_value=collection,
                ):
                    count = bm25_index.sync_from_chroma("knowledge_base")

            self.assertEqual(count, 2)
            self.assertEqual(collection.get_calls, 0)

    def test_count_change_rebuilds_from_chroma(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            collection = FakeCollection([_chunk(1, 0), _chunk(1, 1)])
            with patch.object(settings, "bm25_persist_dir", temp_dir):
                bm25_index.build_index("knowledge_base", [_chunk(1, 0)])
                bm25_index._INDEX_CACHE.clear()
                with patch(
                    "app.services.vectordb.get_collection",
                    return_value=collection,
                ):
                    count = bm25_index.sync_from_chroma("knowledge_base")
                persisted_count = bm25_index._persisted_index_count("knowledge_base")

            self.assertEqual(count, 2)
            self.assertEqual(collection.get_calls, 1)
            self.assertEqual(persisted_count, 2)

    def test_empty_chroma_removes_stale_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            collection = FakeCollection([])
            index_path = Path(temp_dir) / "knowledge_base.pkl"
            with patch.object(settings, "bm25_persist_dir", temp_dir):
                bm25_index.build_index("knowledge_base", [_chunk(1, 0)])
                self.assertTrue(index_path.exists())
                with patch(
                    "app.services.vectordb.get_collection",
                    return_value=collection,
                ):
                    count = bm25_index.sync_from_chroma("knowledge_base")

            self.assertEqual(count, 0)
            self.assertFalse(index_path.exists())


if __name__ == "__main__":
    unittest.main()
