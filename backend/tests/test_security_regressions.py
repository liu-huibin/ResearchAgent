import io
import os
import pickle
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.core import file_permissions
from app.core.security import API_TOKEN_HEADER, ApiSecurityMiddleware
from app.core.storage import UploadValidationError, cleanup_prepared_upload, prepare_upload
from app.core.subprocess_env import safe_subprocess_env
from app.schemas.message import MessageResponse
from app.services import bm25_index


def security_app(token: str = "") -> FastAPI:
    app = FastAPI()

    @app.get("/api/data")
    async def data():
        return {"ok": True}

    @app.delete("/api/data")
    async def delete_data():
        return {"ok": True}

    origins = ("http://127.0.0.1:3000",)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_methods=["GET", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", API_TOKEN_HEADER],
    )
    app.add_middleware(ApiSecurityMiddleware, allowed_origins=origins, api_token=token)
    return app


class SecurityBoundaryTests(unittest.TestCase):
    def test_untrusted_origin_is_rejected_before_read_or_delete(self):
        client = TestClient(security_app())
        for method in (client.get, client.delete):
            response = method("/api/data", headers={"Origin": "https://evil.example"})
            self.assertEqual(response.status_code, 403)

    def test_exact_origin_gets_cors_but_lookalike_does_not(self):
        client = TestClient(security_app())
        allowed = client.options(
            "/api/data",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": API_TOKEN_HEADER,
            },
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "http://127.0.0.1:3000",
        )
        denied = client.get(
            "/api/data", headers={"Origin": "http://127.0.0.1:3000.evil.example"}
        )
        self.assertEqual(denied.status_code, 403)

    def test_configured_token_is_required_and_not_accepted_in_url(self):
        token = "a" * 32
        client = TestClient(security_app(token))
        self.assertEqual(client.get(f"/api/data?token={token}").status_code, 401)
        self.assertEqual(
            client.get("/api/data", headers={API_TOKEN_HEADER: "wrong"}).status_code,
            401,
        )
        self.assertEqual(
            client.get("/api/data", headers={API_TOKEN_HEADER: token}).status_code,
            200,
        )

    def test_weak_configured_token_is_rejected(self):
        with self.assertRaises(ValueError):
            Settings(api_token="short")

    def test_child_environment_excludes_secrets(self):
        with patch.dict(
            os.environ,
            {
                "PATH": "test-path",
                "LLM_API_KEY": "secret-key",
                "OPENAI_API_KEY": "secret-openai",
                "API_TOKEN": "secret-token",
                "MYSQL_PASSWORD": "secret-password",
            },
            clear=True,
        ):
            child = safe_subprocess_env()
        self.assertEqual(child["PATH"], "test-path")
        self.assertFalse(any("secret" in value for value in child.values()))

    def test_historical_message_payload_is_filtered(self):
        response = MessageResponse.model_validate(
            {
                "id": 1,
                "session_id": 1,
                "role": "assistant",
                "content": "answer",
                "thought": "private reasoning",
                "tool_calls": [
                    {
                        "kind": "stage",
                        "agent": "ReaderAgent",
                        "stage": "reader",
                        "detail": "当前依据：会话中已有论文正文。",
                        "report": "结论：已识别论文方法。\n依据：正文证据。",
                        "status": "succeeded",
                        "summary": "private intermediate output",
                    },
                    {
                        "agent": "ReaderAgent",
                        "tool": "read_file",
                        "input": {"path": "secret.pdf"},
                        "output": "private content",
                    }
                ],
                "created_at": datetime.now(),
            }
        ).model_dump()
        self.assertNotIn("thought", response)
        self.assertEqual(
            response["tool_calls"][0]["detail"],
            "当前依据：会话中已有论文正文。",
        )
        self.assertIn("已识别论文方法", response["tool_calls"][0]["report"])
        self.assertNotIn("summary", response["tool_calls"][0])
        self.assertNotIn("input", response["tool_calls"][1])
        self.assertNotIn("output", response["tool_calls"][1])

    def test_recursive_windows_acl_resets_descendants_to_inherit_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "private"
            root.mkdir()
            (root / "document.pdf").write_bytes(b"private")
            completed = SimpleNamespace(returncode=0, stdout="", stderr="")
            with (
                patch.object(file_permissions.os, "name", "nt"),
                patch.object(file_permissions.shutil, "which", side_effect=lambda name: name),
                patch.object(
                    file_permissions, "_windows_principal", return_value="DOMAIN\\user"
                ),
                patch.object(file_permissions.subprocess, "run", return_value=completed) as run,
                patch.dict(file_permissions.os.environ, {}, clear=True),
            ):
                self.assertTrue(file_permissions.harden_private_path(root, recursive=True))

            self.assertEqual(run.call_count, 2)
            root_command = run.call_args_list[0].args[0]
            reset_command = run.call_args_list[1].args[0]
            self.assertNotIn("/T", root_command)
            self.assertIn("DOMAIN\\user:(OI)(CI)F", root_command)
            self.assertEqual(reset_command[1], str(root.resolve() / "*"))
            self.assertEqual(reset_command[2:], ["/reset", "/T", "/C", "/Q"])


class UploadSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_limit_rejects_oversized_file_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upload = UploadFile(filename="large.pdf", file=io.BytesIO(b"%PDF-" + b"x" * (1024 * 1024)))
            with (
                patch.object(settings, "upload_dir", temp_dir),
                patch.object(settings, "max_upload_size_mb", 1),
            ):
                with self.assertRaises(UploadValidationError):
                    await prepare_upload(upload)
            self.assertEqual(list(Path(temp_dir).rglob("upload_*")), [])

    async def test_pdf_extension_with_wrong_signature_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upload = UploadFile(filename="fake.pdf", file=io.BytesIO(b"not a pdf"))
            with patch.object(settings, "upload_dir", temp_dir):
                with self.assertRaises(UploadValidationError):
                    await prepare_upload(upload)

    async def test_docx_zip_bomb_ratio_is_rejected(self):
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", "x" * 100_000)
        with tempfile.TemporaryDirectory() as temp_dir:
            upload = UploadFile(filename="bomb.docx", file=io.BytesIO(content.getvalue()))
            with (
                patch.object(settings, "upload_dir", temp_dir),
                patch.object(settings, "max_docx_compression_ratio", 2),
            ):
                with self.assertRaises(UploadValidationError):
                    await prepare_upload(upload)


class BM25SecurityTests(unittest.TestCase):
    def test_legacy_pickle_is_never_loaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy = Path(temp_dir) / "knowledge_base.pkl"
            with legacy.open("wb") as stream:
                pickle.dump({"corpus": ["legacy"]}, stream)
            with patch.object(settings, "bm25_persist_dir", temp_dir):
                bm25_index._INDEX_CACHE.clear()
                self.assertIsNone(bm25_index._get_or_load_index("knowledge_base"))
                self.assertTrue(legacy.exists())


if __name__ == "__main__":
    unittest.main()
