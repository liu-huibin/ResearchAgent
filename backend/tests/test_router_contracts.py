import io
import unittest
from datetime import datetime

from fastapi import HTTPException, UploadFile

from app.main import app
from app.models.session import Session
from app.models.workflow_run import WorkflowRun
from app.routers.documents import serve_document_file, upload_session_document
from app.routers.knowledge import upload_knowledge
from app.routers.messages import get_session_metrics


class FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class FakeExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return FakeScalarResult(self._values)


class FakeSession:
    def __init__(self, session=None, execute_values=None):
        self.session = session
        self.execute_values = execute_values or []

    async def get(self, model, _object_id):
        if model is Session:
            return self.session
        return None

    async def execute(self, _statement):
        return FakeExecuteResult(self.execute_values)


class RouterContractTests(unittest.IsolatedAsyncioTestCase):
    def test_public_api_paths_match_the_current_frontend_contract(self):
        actual = {
            (method, route.path)
            for route in app.routes
            for method in getattr(route, "methods", set())
        }
        expected = {
            ("GET", "/api/health"),
            ("POST", "/api/sessions"),
            ("GET", "/api/sessions"),
            ("DELETE", "/api/sessions/{session_id}"),
            ("PATCH", "/api/sessions/{session_id}"),
            ("POST", "/api/sessions/{session_id}/upload"),
            ("GET", "/api/sessions/{session_id}/document"),
            ("GET", "/api/documents/{document_id}/file"),
            ("POST", "/api/sessions/{session_id}/messages"),
            ("GET", "/api/sessions/{session_id}/messages"),
            ("GET", "/api/sessions/{session_id}/metrics"),
            ("POST", "/api/knowledge/upload"),
            ("DELETE", "/api/knowledge/{doc_id}"),
            ("GET", "/api/knowledge/list"),
        }

        self.assertTrue(expected.issubset(actual))

    async def test_session_metrics_aggregates_runs_and_keeps_latest_first(self):
        now = datetime.now()
        runs = [
            WorkflowRun(
                id=2,
                session_id=7,
                trace_id="00000000-0000-0000-0000-000000000002",
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
                started_at=now,
                completed_at=now,
            ),
            WorkflowRun(
                id=1,
                session_id=7,
                trace_id="00000000-0000-0000-0000-000000000001",
                input_tokens=3,
                output_tokens=4,
                total_tokens=7,
                started_at=now,
                completed_at=now,
            ),
        ]
        db = FakeSession(Session(id=7), runs)

        metrics = await get_session_metrics(7, db)

        self.assertEqual(metrics.input_tokens, 13)
        self.assertEqual(metrics.output_tokens, 24)
        self.assertEqual(metrics.total_tokens, 37)
        self.assertEqual(metrics.run_count, 2)
        self.assertEqual(metrics.latest_run.id, 2)

    async def test_session_document_upload_rejects_unsupported_extension(self):
        upload = UploadFile(filename="notes.txt", file=io.BytesIO(b"notes"))
        db = FakeSession(Session(id=7))

        with self.assertRaises(HTTPException) as caught:
            await upload_session_document(7, upload, db)

        self.assertEqual(caught.exception.status_code, 400)

    async def test_knowledge_upload_rejects_unsupported_extension(self):
        upload = UploadFile(filename="notes.txt", file=io.BytesIO(b"notes"))

        with self.assertRaises(HTTPException) as caught:
            await upload_knowledge(upload, FakeSession())

        self.assertEqual(caught.exception.status_code, 400)

    async def test_document_download_returns_not_found_for_unknown_document(self):
        with self.assertRaises(HTTPException) as caught:
            await serve_document_file(99, FakeSession())

        self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
