import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from scripts.kms_preflight import (
    collect_knowledge_inventory,
    compare_schema,
    parse_init_db_schema,
    validate_backup,
)


class KMSPreflightTests(unittest.TestCase):
    def test_init_db_parser_captures_tables_indexes_and_delayed_foreign_key(self):
        sql = (Path(__file__).resolve().parents[1] / "init_db.sql").read_text(
            encoding="utf-8"
        )
        schema = parse_init_db_schema(sql)

        self.assertEqual(schema["database"]["character_set"], "utf8mb4")
        self.assertEqual(
            set(schema["tables"]),
            {"users", "documents", "sessions", "messages", "workflow_runs"},
        )
        self.assertIn("file_md5", schema["tables"]["documents"]["columns"])
        self.assertTrue(
            any(
                foreign_key["column"] == "session_id"
                and foreign_key["referenced_table"] == "sessions"
                for foreign_key in schema["tables"]["documents"]["foreign_keys"]
            )
        )
        self.assertTrue(
            any(
                index["columns"] == ["trace_id"] and index["unique"]
                for index in schema["tables"]["workflow_runs"]["indexes"]
            )
        )

    def test_schema_comparison_reports_missing_and_incompatible_columns(self):
        actual = {
            "tables": {
                "papers": {
                    "columns": {
                        "id": {"data_type": "int", "length": None, "nullable": False},
                        "title": {"data_type": "text", "length": None, "nullable": True},
                    },
                    "indexes": [],
                    "foreign_keys": [],
                }
            }
        }
        expected = {
            "tables": {
                "papers": {
                    "columns": {
                        "id": {"data_type": "int", "length": None, "nullable": False},
                        "title": {"data_type": "varchar", "length": 255, "nullable": False},
                        "file_md5": {"data_type": "varchar", "length": 32, "nullable": False},
                    },
                    "indexes": [],
                    "foreign_keys": [],
                }
            }
        }

        differences = compare_schema(actual, expected, "fixture")
        kinds = {(item["kind"], item.get("column")) for item in differences}

        self.assertIn(("missing_column", "file_md5"), kinds)
        self.assertIn(("column_type", "title"), kinds)
        self.assertIn(("column_nullable", "title"), kinds)

    def test_backup_validation_requires_header_and_completion_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            valid_path = Path(temp_dir) / "valid.sql"
            valid_path.write_bytes(
                b"-- MySQL dump 10.13\nCREATE TABLE example(id INT);\n-- Dump completed\n"
            )
            invalid_path = Path(temp_dir) / "invalid.sql"
            invalid_path.write_text("SELECT 1;\n", encoding="utf-8")

            self.assertTrue(validate_backup(valid_path)["valid"])
            self.assertFalse(validate_backup(invalid_path)["valid"])

    def test_inventory_reads_chroma_without_changing_its_sqlite_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            chroma_dir = root / "chroma"
            bm25_dir = root / "bm25"
            chroma_dir.mkdir()
            bm25_dir.mkdir()
            sqlite_path = chroma_dir / "chroma.sqlite3"
            connection = sqlite3.connect(sqlite_path)
            connection.executescript(
                """
                CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE segments (
                    id TEXT PRIMARY KEY, type TEXT NOT NULL,
                    scope TEXT NOT NULL, collection TEXT NOT NULL
                );
                CREATE TABLE embeddings (
                    id INTEGER PRIMARY KEY, segment_id TEXT NOT NULL,
                    embedding_id TEXT NOT NULL
                );
                CREATE TABLE embedding_metadata (
                    id INTEGER NOT NULL, key TEXT NOT NULL,
                    string_value TEXT, int_value INTEGER,
                    float_value REAL, bool_value INTEGER,
                    PRIMARY KEY (id, key)
                );
                INSERT INTO collections (id, name) VALUES ('collection-1', 'knowledge_base');
                INSERT INTO segments (id, type, scope, collection)
                    VALUES ('segment-1', 'metadata', 'METADATA', 'collection-1');
                INSERT INTO embeddings (id, segment_id, embedding_id)
                    VALUES (1, 'segment-1', 'chunk-1'), (2, 'segment-1', 'chunk-2');
                INSERT INTO embedding_metadata (id, key, int_value)
                    VALUES (1, 'document_id', 7), (2, 'document_id', 7);
                """
            )
            connection.commit()
            connection.close()

            document_path = root / "paper.pdf"
            document_path.write_bytes(b"synthetic-paper")
            checksum = hashlib.md5(document_path.read_bytes()).hexdigest()
            with (bm25_dir / "knowledge_base.json").open("w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "format_version": 1,
                        "corpus": ["first", "second"],
                        "tokenized_corpus": [["first"], ["second"]],
                        "metadatas": [
                            {"document_id": 7},
                            {"document_id": 7},
                        ],
                    },
                    stream,
                )
            sqlite_hash_before = hashlib.sha256(sqlite_path.read_bytes()).hexdigest()

            with (
                patch.object(settings, "chroma_persist_dir", str(chroma_dir)),
                patch.object(settings, "bm25_persist_dir", str(bm25_dir)),
            ):
                inventory = collect_knowledge_inventory(
                    [
                        {
                            "id": 7,
                            "filename": "paper.pdf",
                            "file_path": str(document_path),
                            "file_md5": checksum,
                        }
                    ]
                )

            sqlite_hash_after = hashlib.sha256(sqlite_path.read_bytes()).hexdigest()
            self.assertEqual(sqlite_hash_before, sqlite_hash_after)
            self.assertEqual(inventory["chroma"]["chunks"], 2)
            self.assertEqual(inventory["bm25"]["chunks"], 2)
            self.assertEqual(inventory["records"][0]["chroma_chunks"], 2)
            self.assertEqual(inventory["records"][0]["bm25_chunks"], 2)
            self.assertEqual(inventory["anomalies"], [])


if __name__ == "__main__":
    unittest.main()
