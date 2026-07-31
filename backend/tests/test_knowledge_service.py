import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.models.document import Document
from app.services.knowledge import service as knowledge_service


class FakeScalarResult:
    def first(self):
        return None


class FakeExecuteResult:
    def scalars(self):
        return FakeScalarResult()


class FakeKnowledgeDatabase:
    def __init__(self):
        self.added = []
        self.rollbacks = 0

    async def execute(self, _statement):
        return FakeExecuteResult()

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if isinstance(value, Document) and value.id is None:
                value.id = 13

    async def refresh(self, _value):
        return None

    async def rollback(self):
        self.rollbacks += 1


class KnowledgeServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_document_rolls_back_indexes_and_new_file(self):
        database = FakeKnowledgeDatabase()
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(settings, "upload_dir", temp_dir),
                patch.object(knowledge_service, "extract_text_from_file", return_value=""),
                patch.object(knowledge_service, "delete_vectordb_doc") as delete_vector,
                patch.object(knowledge_service, "remove_from_bm25") as remove_bm25,
            ):
                with self.assertRaises(knowledge_service.EmptyDocumentError):
                    await knowledge_service.upload_knowledge(
                        database,
                        filename="empty.pdf",
                        content=b"%PDF-empty",
                    )

            self.assertEqual(database.rollbacks, 1)
            delete_vector.assert_called_once_with(13)
            remove_bm25.assert_called_once_with("knowledge_base", 13)
            self.assertEqual(list(Path(temp_dir).rglob("*.pdf")), [])


if __name__ == "__main__":
    unittest.main()
