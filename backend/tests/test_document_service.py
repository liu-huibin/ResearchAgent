import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.models.document import Document
from app.models.session import Session
from app.services.documents.service import upload_session_document


class FakeDocumentDatabase:
    def __init__(self, fail_commit=False):
        self.session = Session(id=7)
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_commit = fail_commit

    async def get(self, model, _object_id):
        if model is Session:
            return self.session
        return None

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        for value in self.added:
            if isinstance(value, Document) and value.id is None:
                value.id = 11

    async def refresh(self, _value):
        return None

    async def commit(self):
        self.commits += 1
        if self.fail_commit:
            raise RuntimeError("database unavailable")

    async def rollback(self):
        self.rollbacks += 1


class DocumentServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_uses_one_transaction_and_sets_active_document(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = FakeDocumentDatabase()
            with patch.object(settings, "upload_dir", temp_dir):
                document = await upload_session_document(
                    database,
                    session_id=7,
                    filename="paper.pdf",
                    content=b"%PDF-sample",
                )

            self.assertEqual(database.commits, 1)
            self.assertEqual(database.rollbacks, 0)
            self.assertEqual(database.session.active_document_id, 11)
            self.assertTrue(Path(document.file_path).is_file())

    async def test_upload_failure_rolls_back_and_removes_new_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = FakeDocumentDatabase(fail_commit=True)
            with patch.object(settings, "upload_dir", temp_dir):
                with self.assertRaises(RuntimeError):
                    await upload_session_document(
                        database,
                        session_id=7,
                        filename="paper.pdf",
                        content=b"%PDF-sample",
                    )

            self.assertEqual(database.rollbacks, 1)
            self.assertEqual(list(Path(temp_dir).rglob("*.pdf")), [])


if __name__ == "__main__":
    unittest.main()
