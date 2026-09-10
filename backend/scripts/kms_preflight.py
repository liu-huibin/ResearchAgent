"""KMS development preflight gate.

This command is intentionally separate from application startup.  It inspects
the configured MySQL database through a read-only session, creates a logical
backup with ``mysqldump``, inventories the legacy knowledge stores, exercises
the four KMS dependencies, and records the existing regression baseline.

Secrets and document contents are never serialized into the generated JSON or
Markdown evidence.  The logical SQL backup is written to an ignored directory.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.core.config import settings  # noqa: E402
from app.core.file_permissions import harden_private_path  # noqa: E402
from app.core.subprocess_env import safe_subprocess_env  # noqa: E402


SQL_COLUMN_SKIP = {
    "PRIMARY",
    "INDEX",
    "KEY",
    "UNIQUE",
    "CONSTRAINT",
    "FOREIGN",
    "CHECK",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "__float__"):
        return float(value)
    return str(value)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - compatibility inventory, not security
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_backend_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path.resolve()


def split_sql_items(body: str) -> list[str]:
    """Split a CREATE TABLE body on top-level commas."""

    result: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(body):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            result.append(body[start:index].strip())
            start = index + 1
    tail = body[start:].strip()
    if tail:
        result.append(tail)
    return result


def _matching_parenthesis(sql: str, opening: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(sql)):
        char = sql[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("Unbalanced CREATE TABLE statement")


def parse_init_db_schema(sql: str) -> dict[str, Any]:
    """Extract comparable tables, columns, indexes, and foreign keys."""

    tables: dict[str, dict[str, Any]] = {}
    table_pattern = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?(\w+)`?\s*\(",
        re.IGNORECASE,
    )
    for match in table_pattern.finditer(sql):
        table_name = match.group(1)
        opening = match.end() - 1
        closing = _matching_parenthesis(sql, opening)
        body = sql[opening + 1 : closing]
        columns: dict[str, dict[str, Any]] = {}
        indexes: list[dict[str, Any]] = []
        foreign_keys: list[dict[str, Any]] = []
        for item in split_sql_items(body):
            compact = " ".join(item.split())
            first = compact.lstrip("`").split(None, 1)[0].rstrip("`").upper()
            column_match = re.match(r"`?(\w+)`?\s+([A-Z]+)(?:\(([^)]*)\))?", compact, re.I)
            if first not in SQL_COLUMN_SKIP and column_match:
                type_name = column_match.group(2).lower()
                length_value = column_match.group(3)
                length = int(length_value) if length_value and length_value.isdigit() else None
                columns[column_match.group(1)] = {
                    "data_type": type_name,
                    "length": length,
                    "nullable": not bool(
                        re.search(r"\b(?:NOT\s+NULL|PRIMARY\s+KEY)\b", compact, re.I)
                    ),
                }
                continue

            index_match = re.match(
                r"(?:(UNIQUE)\s+)?(?:INDEX|KEY)\s+`?(\w+)`?\s*\(([^)]+)\)",
                compact,
                re.I,
            )
            if index_match:
                indexes.append(
                    {
                        "name": index_match.group(2),
                        "unique": bool(index_match.group(1)),
                        "columns": [
                            part.strip().strip("`").split("(", 1)[0]
                            for part in index_match.group(3).split(",")
                        ],
                    }
                )

            fk_match = re.search(
                r"(?:CONSTRAINT\s+`?(\w+)`?\s+)?FOREIGN\s+KEY\s*\(`?(\w+)`?\)"
                r"\s+REFERENCES\s+`?(\w+)`?\s*\(`?(\w+)`?\)"
                r"(?:\s+ON\s+DELETE\s+(CASCADE|SET\s+NULL|RESTRICT|NO\s+ACTION))?",
                compact,
                re.I,
            )
            if fk_match:
                foreign_keys.append(
                    {
                        "name": fk_match.group(1) or "",
                        "column": fk_match.group(2),
                        "referenced_table": fk_match.group(3),
                        "referenced_column": fk_match.group(4),
                        "delete_rule": (fk_match.group(5) or "").upper(),
                    }
                )
        tables[table_name] = {
            "columns": columns,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
        }

    # init_db.sql adds the reverse documents -> sessions FK after both tables
    # exist.  Capture ALTER TABLE constraints as part of the expected schema.
    alter_pattern = re.compile(
        r"ALTER\s+TABLE\s+`?(\w+)`?\s+ADD\s+CONSTRAINT\s+`?(\w+)`?\s+"
        r"FOREIGN\s+KEY\s*\(`?(\w+)`?\)\s+REFERENCES\s+`?(\w+)`?\s*"
        r"\(`?(\w+)`?\)(?:\s+ON\s+DELETE\s+(CASCADE|SET\s+NULL|RESTRICT|NO\s+ACTION))?",
        re.I,
    )
    for match in alter_pattern.finditer(sql):
        if match.group(1) in tables:
            tables[match.group(1)]["foreign_keys"].append(
                {
                    "name": match.group(2),
                    "column": match.group(3),
                    "referenced_table": match.group(4),
                    "referenced_column": match.group(5),
                    "delete_rule": (match.group(6) or "").upper(),
                }
            )

    database_match = re.search(
        r"CREATE\s+DATABASE.*?CHARACTER\s+SET\s+(\w+).*?COLLATE\s+(\w+)",
        sql,
        re.I | re.S,
    )
    return {
        "database": {
            "character_set": database_match.group(1) if database_match else None,
            "collation": database_match.group(2) if database_match else None,
        },
        "tables": tables,
    }


def model_schema() -> dict[str, Any]:
    from sqlmodel import SQLModel
    from app import models as _models  # noqa: F401

    tables: dict[str, Any] = {}
    for table in sorted(SQLModel.metadata.tables.values(), key=lambda item: item.name):
        columns: dict[str, Any] = {}
        for column in table.columns:
            type_name = type(column.type).__name__.lower()
            if type_name in {"integer", "biginteger", "smallinteger"}:
                type_name = type_name.replace("integer", "int")
            elif type_name in {"string", "autostring"}:
                type_name = "varchar"
            columns[column.name] = {
                "data_type": type_name,
                "length": getattr(column.type, "length", None),
                "nullable": bool(column.nullable),
            }
        indexes = [
            {
                "name": index.name or "",
                "unique": bool(index.unique),
                "columns": [column.name for column in index.columns],
            }
            for index in table.indexes
        ]
        foreign_keys = []
        for column in table.columns:
            for foreign_key in column.foreign_keys:
                foreign_keys.append(
                    {
                        "name": foreign_key.constraint.name or "",
                        "column": column.name,
                        "referenced_table": foreign_key.column.table.name,
                        "referenced_column": foreign_key.column.name,
                        "delete_rule": (foreign_key.ondelete or "").upper(),
                    }
                )
        tables[table.name] = {
            "columns": columns,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
        }
    return {"tables": tables}


def _type_compatible(expected: str, actual: str) -> bool:
    aliases = {
        "boolean": {"boolean", "bool", "tinyint"},
        "bool": {"boolean", "bool", "tinyint"},
        "integer": {"integer", "int"},
        "int": {"integer", "int"},
    }
    return actual in aliases.get(expected, {expected})


def _index_signatures(indexes: Iterable[dict[str, Any]]) -> set[tuple[Any, ...]]:
    return {
        (bool(index.get("unique")), tuple(index.get("columns", [])))
        for index in indexes
        if index.get("columns")
    }


def _fk_signatures(
    foreign_keys: Iterable[dict[str, Any]],
    include_delete_rule: bool,
) -> set[tuple[Any, ...]]:
    result = set()
    for foreign_key in foreign_keys:
        signature: tuple[Any, ...] = (
            foreign_key.get("column"),
            foreign_key.get("referenced_table"),
            foreign_key.get("referenced_column"),
        )
        if include_delete_rule:
            signature += (foreign_key.get("delete_rule", "").upper(),)
        result.add(signature)
    return result


def compare_schema(
    actual: dict[str, Any],
    expected: dict[str, Any],
    authority: str,
    *,
    include_delete_rule: bool = False,
) -> list[dict[str, Any]]:
    """Return structured schema differences against one authority."""

    differences: list[dict[str, Any]] = []
    actual_tables = actual.get("tables", {})
    expected_tables = expected.get("tables", {})
    for table_name in sorted(set(expected_tables) - set(actual_tables)):
        differences.append(
            {"authority": authority, "kind": "missing_table", "table": table_name}
        )
    for table_name in sorted(set(actual_tables) - set(expected_tables)):
        differences.append(
            {"authority": authority, "kind": "unexpected_table", "table": table_name}
        )
    for table_name in sorted(set(actual_tables) & set(expected_tables)):
        actual_table = actual_tables[table_name]
        expected_table = expected_tables[table_name]
        actual_columns = actual_table.get("columns", {})
        expected_columns = expected_table.get("columns", {})
        for column_name in sorted(set(expected_columns) - set(actual_columns)):
            differences.append(
                {
                    "authority": authority,
                    "kind": "missing_column",
                    "table": table_name,
                    "column": column_name,
                }
            )
        for column_name in sorted(set(actual_columns) - set(expected_columns)):
            differences.append(
                {
                    "authority": authority,
                    "kind": "unexpected_column",
                    "table": table_name,
                    "column": column_name,
                }
            )
        for column_name in sorted(set(actual_columns) & set(expected_columns)):
            actual_column = actual_columns[column_name]
            expected_column = expected_columns[column_name]
            expected_type = str(expected_column.get("data_type", "")).lower()
            actual_type = str(actual_column.get("data_type", "")).lower()
            if expected_type and not _type_compatible(expected_type, actual_type):
                differences.append(
                    {
                        "authority": authority,
                        "kind": "column_type",
                        "table": table_name,
                        "column": column_name,
                        "expected": expected_type,
                        "actual": actual_type,
                    }
                )
            expected_length = expected_column.get("length")
            actual_length = actual_column.get("length")
            if expected_length and int(expected_length) != int(actual_length or 0):
                differences.append(
                    {
                        "authority": authority,
                        "kind": "column_length",
                        "table": table_name,
                        "column": column_name,
                        "expected": expected_length,
                        "actual": actual_length,
                    }
                )
            if bool(expected_column.get("nullable")) != bool(actual_column.get("nullable")):
                differences.append(
                    {
                        "authority": authority,
                        "kind": "column_nullable",
                        "table": table_name,
                        "column": column_name,
                        "expected": bool(expected_column.get("nullable")),
                        "actual": bool(actual_column.get("nullable")),
                    }
                )

        actual_indexes = _index_signatures(actual_table.get("indexes", []))
        expected_indexes = _index_signatures(expected_table.get("indexes", []))
        for signature in sorted(expected_indexes - actual_indexes, key=str):
            differences.append(
                {
                    "authority": authority,
                    "kind": "missing_index",
                    "table": table_name,
                    "unique": signature[0],
                    "columns": list(signature[1]),
                }
            )

        actual_foreign_key_rows = actual_table.get("foreign_keys", [])
        expected_foreign_key_rows = expected_table.get("foreign_keys", [])
        actual_foreign_keys = _fk_signatures(actual_foreign_key_rows, include_delete_rule)
        expected_foreign_keys = _fk_signatures(expected_foreign_key_rows, include_delete_rule)
        missing_foreign_keys = expected_foreign_keys - actual_foreign_keys
        if include_delete_rule:
            actual_rules = {
                signature[:3]: signature[3] for signature in actual_foreign_keys
            }
            expected_rules = {
                signature[:3]: signature[3] for signature in expected_foreign_keys
            }
            for base_signature in sorted(set(actual_rules) & set(expected_rules), key=str):
                if actual_rules[base_signature] != expected_rules[base_signature]:
                    differences.append(
                        {
                            "authority": authority,
                            "kind": "foreign_key_delete_rule",
                            "table": table_name,
                            "signature": list(base_signature),
                            "expected": expected_rules[base_signature],
                            "actual": actual_rules[base_signature],
                        }
                    )
                    missing_foreign_keys.discard(
                        base_signature + (expected_rules[base_signature],)
                    )
        for signature in sorted(missing_foreign_keys, key=str):
            differences.append(
                {
                    "authority": authority,
                    "kind": "missing_foreign_key",
                    "table": table_name,
                    "signature": list(signature),
                }
            )
    return differences


async def _fetch_rows(connection: Any, statement: str, params: dict | None = None) -> list[dict]:
    result = await connection.execute(text(statement), params or {})
    return [dict(row._mapping) for row in result]


async def collect_database_snapshot() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read the configured database without permitting writes in the session."""

    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args=settings.database_connect_args,
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET SESSION TRANSACTION READ ONLY"))
            server_row = (
                await connection.execute(
                    text(
                        "SELECT VERSION() AS version, DATABASE() AS database_name, "
                        "@@character_set_server AS server_character_set, "
                        "@@collation_server AS server_collation, "
                        "@@character_set_database AS database_character_set, "
                        "@@collation_database AS database_collation"
                    )
                )
            ).mappings().one()
            schema_name = str(server_row["database_name"])
            table_rows = await _fetch_rows(
                connection,
                """
                SELECT TABLE_NAME AS table_name, ENGINE AS engine,
                       TABLE_COLLATION AS collation, TABLE_ROWS AS estimated_rows,
                       DATA_LENGTH AS data_length, INDEX_LENGTH AS index_length
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = :schema_name AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
                """,
                {"schema_name": schema_name},
            )
            columns = await _fetch_rows(
                connection,
                """
                SELECT TABLE_NAME AS table_name, COLUMN_NAME AS column_name,
                       ORDINAL_POSITION AS ordinal_position, DATA_TYPE AS data_type,
                       COLUMN_TYPE AS column_type, CHARACTER_MAXIMUM_LENGTH AS character_maximum_length,
                       IS_NULLABLE AS is_nullable, COLUMN_DEFAULT AS column_default,
                       COLUMN_KEY AS column_key, EXTRA AS extra,
                       CHARACTER_SET_NAME AS character_set, COLLATION_NAME AS collation
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema_name
                ORDER BY TABLE_NAME, ORDINAL_POSITION
                """,
                {"schema_name": schema_name},
            )
            indexes = await _fetch_rows(
                connection,
                """
                SELECT TABLE_NAME AS table_name, INDEX_NAME AS index_name,
                       NON_UNIQUE AS non_unique, SEQ_IN_INDEX AS seq_in_index,
                       COLUMN_NAME AS column_name, INDEX_TYPE AS index_type
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = :schema_name
                ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
                """,
                {"schema_name": schema_name},
            )
            foreign_keys = await _fetch_rows(
                connection,
                """
                SELECT k.TABLE_NAME AS table_name, k.CONSTRAINT_NAME AS constraint_name,
                       k.COLUMN_NAME AS column_name,
                       k.REFERENCED_TABLE_NAME AS referenced_table,
                       k.REFERENCED_COLUMN_NAME AS referenced_column,
                       r.UPDATE_RULE AS update_rule, r.DELETE_RULE AS delete_rule
                FROM information_schema.KEY_COLUMN_USAGE k
                JOIN information_schema.REFERENTIAL_CONSTRAINTS r
                  ON r.CONSTRAINT_SCHEMA = k.CONSTRAINT_SCHEMA
                 AND r.CONSTRAINT_NAME = k.CONSTRAINT_NAME
                 AND r.TABLE_NAME = k.TABLE_NAME
                WHERE k.CONSTRAINT_SCHEMA = :schema_name
                  AND k.REFERENCED_TABLE_NAME IS NOT NULL
                ORDER BY k.TABLE_NAME, k.CONSTRAINT_NAME, k.ORDINAL_POSITION
                """,
                {"schema_name": schema_name},
            )
            exact_counts: dict[str, int] = {}
            for table in table_rows:
                table_name = str(table["table_name"])
                if not re.fullmatch(r"[A-Za-z0-9_]+", table_name):
                    raise ValueError(f"Unsafe table name returned by MySQL: {table_name!r}")
                row = (
                    await connection.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))
                ).one()
                exact_counts[table_name] = int(row[0])
            knowledge_documents = await _fetch_rows(
                connection,
                """
                SELECT id, filename, file_path, file_md5, created_at
                FROM documents
                WHERE type = 'knowledge'
                ORDER BY id
                """,
            ) if "documents" in exact_counts else []
            await connection.rollback()
    finally:
        await engine.dispose()

    grouped_columns: dict[str, dict[str, Any]] = defaultdict(dict)
    for column in columns:
        grouped_columns[str(column["table_name"])][str(column["column_name"])] = {
            "ordinal_position": int(column["ordinal_position"]),
            "data_type": str(column["data_type"]).lower(),
            "column_type": str(column["column_type"]),
            "length": column["character_maximum_length"],
            "nullable": column["is_nullable"] == "YES",
            "default": column["column_default"],
            "key": column["column_key"],
            "extra": column["extra"],
            "character_set": column["character_set"],
            "collation": column["collation"],
        }
    grouped_indexes: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for index_row in indexes:
        table_name = str(index_row["table_name"])
        index_name = str(index_row["index_name"])
        entry = grouped_indexes[table_name].setdefault(
            index_name,
            {
                "name": index_name,
                "unique": not bool(index_row["non_unique"]),
                "index_type": index_row["index_type"],
                "columns": [],
            },
        )
        entry["columns"].append(str(index_row["column_name"]))
    grouped_foreign_keys: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for foreign_key in foreign_keys:
        grouped_foreign_keys[str(foreign_key["table_name"])].append(
            {
                "name": foreign_key["constraint_name"],
                "column": foreign_key["column_name"],
                "referenced_table": foreign_key["referenced_table"],
                "referenced_column": foreign_key["referenced_column"],
                "update_rule": foreign_key["update_rule"],
                "delete_rule": foreign_key["delete_rule"],
            }
        )

    table_metadata = {str(row["table_name"]): row for row in table_rows}
    tables: dict[str, Any] = {}
    for table_name in sorted(table_metadata):
        metadata = table_metadata[table_name]
        tables[table_name] = {
            "engine": metadata["engine"],
            "collation": metadata["collation"],
            "estimated_rows": metadata["estimated_rows"],
            "exact_rows": exact_counts[table_name],
            "data_length": int(metadata["data_length"] or 0),
            "index_length": int(metadata["index_length"] or 0),
            "columns": grouped_columns[table_name],
            "indexes": list(grouped_indexes[table_name].values()),
            "foreign_keys": grouped_foreign_keys[table_name],
        }
    snapshot = {
        "captured_at": utc_now(),
        "connection_mode": "SET SESSION TRANSACTION READ ONLY",
        "server": dict(server_row),
        "tables": tables,
        "totals": {
            "table_count": len(tables),
            "row_count": sum(exact_counts.values()),
            "data_length": sum(table["data_length"] for table in tables.values()),
            "index_length": sum(table["index_length"] for table in tables.values()),
        },
    }
    return snapshot, knowledge_documents


def _metadata_document_counts(metadatas: Iterable[Any]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for metadata in metadatas:
        if isinstance(metadata, dict) and metadata.get("document_id") is not None:
            try:
                counts[int(metadata["document_id"])] += 1
            except (TypeError, ValueError):
                continue
    return counts


def collect_knowledge_inventory(knowledge_documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Relate legacy DB rows to their files, Chroma chunks, and BM25 corpus."""

    chroma_error = ""
    chroma_counts: Counter[int] = Counter()
    chroma_total = 0
    try:
        chroma_path = resolve_backend_path(settings.chroma_persist_dir)
        sqlite_path = chroma_path / "chroma.sqlite3"
        # Chroma's PersistentClient performs housekeeping writes even for a
        # get/count call.  Read its metadata segment directly through SQLite's
        # immutable mode so this inventory cannot modify the legacy index.
        connection = sqlite3.connect(
            f"file:{sqlite_path.as_posix()}?mode=ro&immutable=1",
            uri=True,
        )
        try:
            collection_row = connection.execute(
                "SELECT id FROM collections WHERE name = ?",
                ("knowledge_base",),
            ).fetchone()
            if collection_row is None:
                raise LookupError("Chroma collection knowledge_base does not exist")
            collection_id = str(collection_row[0])
            chroma_total = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM embeddings e
                    JOIN segments s ON s.id = e.segment_id
                    WHERE s.collection = ? AND s.scope = 'METADATA'
                    """,
                    (collection_id,),
                ).fetchone()[0]
            )
            count_rows = connection.execute(
                """
                SELECT COALESCE(m.int_value, CAST(m.string_value AS INTEGER)) AS document_id,
                       COUNT(*) AS chunk_count
                FROM embeddings e
                JOIN segments s ON s.id = e.segment_id
                JOIN embedding_metadata m ON m.id = e.id AND m.key = 'document_id'
                WHERE s.collection = ? AND s.scope = 'METADATA'
                GROUP BY COALESCE(m.int_value, CAST(m.string_value AS INTEGER))
                """,
                (collection_id,),
            ).fetchall()
            chroma_counts = Counter(
                {int(document_id): int(count) for document_id, count in count_rows}
            )
        finally:
            connection.close()
    except Exception as exc:  # inventory must report store failures, not hide them
        chroma_error = f"{type(exc).__name__}: {exc}"

    bm25_error = ""
    bm25_counts: Counter[int] = Counter()
    bm25_total = 0
    bm25_components: dict[str, int] = {}
    bm25_path = resolve_backend_path(settings.bm25_persist_dir) / "knowledge_base.json"
    legacy_bm25_path = resolve_backend_path(settings.bm25_persist_dir) / "knowledge_base.pkl"
    try:
        with bm25_path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or data.get("format_version") != 1:
            raise ValueError("unsupported BM25 JSON format")
        corpus = data.get("corpus", [])
        metadatas = data.get("metadatas", [])
        tokenized = data.get("tokenized_corpus", [])
        if not all(isinstance(value, list) for value in (corpus, metadatas, tokenized)):
            raise ValueError("invalid BM25 JSON components")
        bm25_total = len(corpus)
        bm25_components = {
            "corpus": len(corpus),
            "metadatas": len(metadatas),
            "tokenized_corpus": len(tokenized),
        }
        bm25_counts = _metadata_document_counts(metadatas)
    except Exception as exc:
        bm25_error = f"{type(exc).__name__}: {exc}"

    md5_groups: dict[str, list[int]] = defaultdict(list)
    records: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    database_ids: set[int] = set()
    for document in knowledge_documents:
        document_id = int(document["id"])
        database_ids.add(document_id)
        stored_md5 = str(document.get("file_md5") or "").lower()
        md5_groups[stored_md5].append(document_id)
        absolute_path = resolve_backend_path(str(document.get("file_path") or ""))
        exists = absolute_path.is_file()
        actual_md5 = md5_file(absolute_path) if exists else None
        record = {
            "document_id": document_id,
            "filename": document.get("filename"),
            "stored_path": document.get("file_path"),
            "resolved_path": str(absolute_path),
            "file_exists": exists,
            "file_size": absolute_path.stat().st_size if exists else None,
            "stored_md5": stored_md5,
            "actual_md5": actual_md5,
            "md5_matches": bool(exists and actual_md5 == stored_md5),
            "chroma_chunks": int(chroma_counts.get(document_id, 0)),
            "bm25_chunks": int(bm25_counts.get(document_id, 0)),
        }
        records.append(record)
        if not exists:
            anomalies.append({"kind": "missing_file", "document_id": document_id})
        elif actual_md5 != stored_md5:
            anomalies.append({"kind": "file_md5_mismatch", "document_id": document_id})
        if record["chroma_chunks"] != record["bm25_chunks"]:
            anomalies.append(
                {
                    "kind": "index_chunk_count_mismatch",
                    "document_id": document_id,
                    "chroma": record["chroma_chunks"],
                    "bm25": record["bm25_chunks"],
                }
            )

    duplicate_md5 = [
        {"md5": checksum, "document_ids": ids}
        for checksum, ids in sorted(md5_groups.items())
        if checksum and len(ids) > 1
    ]
    for group in duplicate_md5:
        anomalies.append({"kind": "duplicate_database_md5", **group})
    for document_id in sorted(set(chroma_counts) - database_ids):
        anomalies.append(
            {
                "kind": "orphan_chroma_document",
                "document_id": document_id,
                "chunks": chroma_counts[document_id],
            }
        )
    for document_id in sorted(set(bm25_counts) - database_ids):
        anomalies.append(
            {
                "kind": "orphan_bm25_document",
                "document_id": document_id,
                "chunks": bm25_counts[document_id],
            }
        )

    if chroma_error:
        anomalies.append({"kind": "chroma_unreadable", "detail": chroma_error})
    if bm25_error:
        anomalies.append({"kind": "bm25_unreadable", "detail": bm25_error})
    if bm25_components and len(set(bm25_components.values())) != 1:
        anomalies.append({"kind": "bm25_component_count_mismatch", **bm25_components})

    return {
        "captured_at": utc_now(),
        "database_knowledge_documents": len(knowledge_documents),
        "existing_files": sum(1 for record in records if record["file_exists"]),
        "matching_file_md5": sum(1 for record in records if record["md5_matches"]),
        "duplicate_md5_groups": duplicate_md5,
        "chroma": {
            "persist_dir": str(resolve_backend_path(settings.chroma_persist_dir)),
            "collection": "knowledge_base",
            "chunks": chroma_total,
            "error": chroma_error or None,
        },
        "bm25": {
            "path": str(bm25_path),
            "legacy_pickle_present": legacy_bm25_path.is_file(),
            "chunks": bm25_total,
            "components": bm25_components,
            "error": bm25_error or None,
        },
        "records": records,
        "anomalies": anomalies,
    }


def find_executable(name: str, env_name: str, known_paths: Iterable[Path] = ()) -> Path:
    configured = os.environ.get(env_name)
    candidates = [Path(configured)] if configured else []
    discovered = shutil.which(name)
    if discovered:
        candidates.append(Path(discovered))
    candidates.extend(known_paths)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"{name} was not found; set {env_name}")


def validate_backup(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(min(size, 64 * 1024))
        if size > 64 * 1024:
            stream.seek(max(0, size - 64 * 1024))
        else:
            stream.seek(0)
        trailer = stream.read(64 * 1024)
    readable = bool(header)
    header_valid = b"MySQL dump" in header
    completion_marker = b"Dump completed" in trailer
    return {
        "readable": readable,
        "header_valid": header_valid,
        "completion_marker": completion_marker,
        "size_bytes": size,
        "sha256": sha256_file(path) if readable else None,
        "valid": readable and header_valid and completion_marker,
    }


def create_database_backup(backup_dir: Path) -> dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir.mkdir(parents=True, exist_ok=True)
    if not harden_private_path(backup_dir, recursive=True):
        raise RuntimeError(f"could not restrict backup directory ACL: {backup_dir}")
    backup_path = backup_dir / f"{settings.mysql_database}_{timestamp}.sql"
    known = [
        Path(r"D:\Program Files\MySQL\MySQL Server 9.0\bin\mysqldump.exe"),
        Path(r"C:\Program Files\MySQL\MySQL Server 9.0\bin\mysqldump.exe"),
    ]
    mysqldump = find_executable("mysqldump", "MYSQLDUMP_PATH", known)
    command = [
        str(mysqldump),
        f"--host={settings.mysql_host}",
        f"--port={settings.mysql_port}",
        f"--user={settings.mysql_user}",
        "--default-character-set=utf8mb4",
        "--single-transaction",
        "--skip-lock-tables",
        "--routines",
        "--events",
        "--triggers",
        "--hex-blob",
        "--no-tablespaces",
        f"--result-file={backup_path}",
        settings.mysql_database,
    ]
    if settings.mysql_require_tls:
        command.insert(-2, "--ssl-mode=VERIFY_IDENTITY" if settings.mysql_ssl_verify else "--ssl-mode=VERIFY_CA")
        if settings.mysql_ssl_ca:
            command.insert(-2, f"--ssl-ca={settings.mysql_ssl_ca}")
    else:
        command.insert(-2, "--ssl-mode=DISABLED")
    environment = safe_subprocess_env({"MYSQL_PWD": settings.effective_mysql_password})
    started = time.monotonic()
    process = subprocess.run(
        command,
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    environment.pop("MYSQL_PWD", None)
    if process.returncode != 0:
        backup_path.unlink(missing_ok=True)
        error_tail = (process.stderr or process.stdout or "unknown mysqldump failure")[-2000:]
        raise RuntimeError(f"mysqldump failed with code {process.returncode}: {error_tail}")
    validation = validate_backup(backup_path)
    if not validation["valid"]:
        raise RuntimeError(f"mysqldump output failed readability validation: {validation}")
    restore_template = (
        "$env:MYSQL_PWD='<set securely>'; "
        f"mysql --host={settings.mysql_host} --port={settings.mysql_port} "
        f"--user={settings.mysql_user} --default-character-set=utf8mb4 "
        "--database=<RESTORE_DATABASE> --execute=\"SOURCE <BACKUP_FILE>\"; "
        "Remove-Item Env:MYSQL_PWD"
    )
    return {
        "success": True,
        "created_at": utc_now(),
        "database": settings.mysql_database,
        "backup_path": str(backup_path.resolve()),
        "mysqldump_path": str(mysqldump),
        "duration_seconds": round(time.monotonic() - started, 3),
        "validation": validation,
        "restore_command_template": restore_template,
        "restore_executed": False,
    }


def _safe_redis_endpoint(url: str) -> dict[str, Any]:
    parsed = urlsplit(url)
    path = parsed.path.lstrip("/")
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname,
        "port": parsed.port or 6379,
        "database": int(path) if path.isdigit() else 0,
        "credentials_present": bool(parsed.username or parsed.password),
    }


def run_dependency_smoke() -> dict[str, Any]:
    """Exercise imports plus a Celery worker, Whoosh, Alembic, and Redis client."""

    result: dict[str, Any] = {"captured_at": utc_now(), "components": {}}
    versions: dict[str, str] = {}
    for distribution in ("redis", "celery", "Whoosh", "alembic", "SQLAlchemy"):
        versions[distribution] = importlib.metadata.version(distribution)
    result["versions"] = versions

    import redis
    from redis.exceptions import RedisError

    redis_url = os.environ.get("KMS_PREFLIGHT_REDIS_URL") or os.environ.get(
        "REDIS_URL", "redis://127.0.0.1:6379/0"
    )
    endpoint = _safe_redis_endpoint(redis_url)
    client = redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=0.75,
        socket_timeout=0.75,
        decode_responses=True,
    )
    redis_server_status = "available"
    redis_server_error: str | None = None
    try:
        if client.ping() is not True:
            raise RuntimeError("Redis PING did not return true")
    except (RedisError, OSError, RuntimeError) as exc:
        redis_server_status = "not_running"
        redis_server_error = type(exc).__name__
    finally:
        client.close()
    result["components"]["redis"] = {
        "success": True,
        "client_created": True,
        "endpoint": endpoint,
        "server_status": redis_server_status,
        "server_error_type": redis_server_error,
        "note": (
            "Redis server is not required until KMS iteration B; the preflight gate "
            "validates the pinned client and records, but does not hide, server availability."
        ),
    }

    from celery import Celery
    from celery.contrib.testing.worker import start_worker

    celery_app = Celery(
        "kms_preflight",
        broker="memory://",
        backend="cache+memory://",
        include=[],
    )
    celery_app.conf.update(
        task_always_eager=False,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        worker_hijack_root_logger=False,
    )

    @celery_app.task(name="kms_preflight.add")
    def add(left: int, right: int) -> int:
        return left + right

    celery_started = time.monotonic()
    with start_worker(
        celery_app,
        pool="threads",
        concurrency=2,
        perform_ping_check=False,
        loglevel="WARNING",
    ):
        task_result = add.delay(19, 23).get(timeout=15, disable_sync_subtasks=False)
    result["components"]["celery"] = {
        "success": task_result == 42,
        "pool": "threads",
        "concurrency": 2,
        "broker": "memory:// (isolated compatibility smoke)",
        "result": task_result,
        "duration_seconds": round(time.monotonic() - celery_started, 3),
    }

    from whoosh import index
    from whoosh.fields import ID, TEXT, Schema
    from whoosh.qparser import QueryParser

    with tempfile.TemporaryDirectory(prefix="kms_whoosh_") as temp_dir:
        schema = Schema(document_id=ID(stored=True, unique=True), content=TEXT(stored=True))
        whoosh_index = index.create_in(temp_dir, schema)
        writer = whoosh_index.writer()
        writer.add_document(document_id="paper-1", content="federated learning privacy")
        writer.add_document(document_id="paper-2", content="knowledge management system")
        writer.commit()
        writer = None
        with whoosh_index.searcher() as searcher:
            query = QueryParser("content", whoosh_index.schema).parse("federated")
            hits = searcher.search(query)
            hit_ids = [hit["document_id"] for hit in hits]
            del hits
        whoosh_index.close()
        del searcher
        del whoosh_index
        gc.collect()
    result["components"]["whoosh"] = {
        "success": hit_ids == ["paper-1"],
        "documents_written": 2,
        "query": "federated",
        "hit_ids": hit_ids,
    }

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import Column, Integer, String

    with tempfile.TemporaryDirectory(prefix="kms_alembic_") as temp_dir:
        database_path = Path(temp_dir) / "migration_smoke.sqlite3"
        sync_engine = create_engine(f"sqlite:///{database_path}")
        try:
            with sync_engine.begin() as connection:
                context = MigrationContext.configure(connection)
                operations = Operations(context)
                operations.create_table(
                    "kms_alembic_smoke",
                    Column("id", Integer, primary_key=True),
                    Column("value", String(32), nullable=False),
                )
            tables_after_upgrade = inspect(sync_engine).get_table_names()
            with sync_engine.begin() as connection:
                context = MigrationContext.configure(connection)
                Operations(context).drop_table("kms_alembic_smoke")
            tables_after_downgrade = inspect(sync_engine).get_table_names()
        finally:
            sync_engine.dispose()
    result["components"]["alembic"] = {
        "success": (
            "kms_alembic_smoke" in tables_after_upgrade
            and "kms_alembic_smoke" not in tables_after_downgrade
        ),
        "upgrade_created_table": "kms_alembic_smoke" in tables_after_upgrade,
        "downgrade_removed_table": "kms_alembic_smoke" not in tables_after_downgrade,
        "database": "temporary SQLite compatibility smoke",
    }
    result["success"] = all(
        bool(component.get("success")) for component in result["components"].values()
    )
    return result


def run_logged_command(
    name: str,
    command: list[str],
    cwd: Path,
    artifact_dir: Path,
    timeout: int,
) -> dict[str, Any]:
    started = time.monotonic()
    environment = safe_subprocess_env(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "LOG_DIR": str(artifact_dir / "runtime_log"),
        }
    )
    process = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    log_path = artifact_dir / f"{name}.log"
    log_path.write_text(
        (process.stdout or "") + ("\n" + process.stderr if process.stderr else ""),
        encoding="utf-8",
    )
    return {
        "success": process.returncode == 0,
        "exit_code": process.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "log_path": str(log_path.resolve()),
    }


async def run_qwen_sse_smoke(artifact_dir: Path) -> dict[str, Any]:
    """Run one real API/SSE workflow and delete its synthetic session."""

    if not settings.llm_api_key:
        return {
            "success": False,
            "reason": "LLM_API_KEY is not visible in the existing environment",
            "credentials_printed": False,
        }

    # Keep the smoke's runtime log out of the tracked historical log directory.
    settings.log_dir = str(artifact_dir / "runtime_log")
    import httpx
    from app.main import app

    session_id: int | None = None
    event_types: list[str] = []
    error_events = 0
    done_payload: dict[str, Any] = {}
    started = time.monotonic()
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://kms-preflight.local",
            timeout=httpx.Timeout(180.0),
        ) as client:
            try:
                created = await client.post(
                    "/api/sessions",
                    json={"title": "KMS preflight smoke"},
                )
                created.raise_for_status()
                session_id = int(created.json()["id"])
                async with client.stream(
                    "POST",
                    f"/api/sessions/{session_id}/messages",
                    json={"content": "只用一句话回答：前置门禁已进入真实问答冒烟。"},
                ) as response:
                    response.raise_for_status()
                    current_event = ""
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            current_event = line.split(":", 1)[1].strip()
                            event_types.append(current_event)
                            if current_event == "error":
                                error_events += 1
                        elif line.startswith("data:") and current_event == "done":
                            done_payload = json.loads(line.split(":", 1)[1].strip())
                metrics = await client.get(f"/api/sessions/{session_id}/metrics")
                metrics.raise_for_status()
                metrics_payload = metrics.json()
            finally:
                cleanup_status = None
                if session_id is not None:
                    cleanup = await client.delete(f"/api/sessions/{session_id}")
                    cleanup_status = cleanup.status_code

    success = (
        "done" in event_types
        and "metrics" in event_types
        and error_events == 0
        and int(done_payload.get("message_id", 0)) > 0
        and int(metrics_payload.get("run_count", 0)) == 1
        and cleanup_status == 204
    )
    return {
        "success": success,
        "duration_seconds": round(time.monotonic() - started, 3),
        "event_types": event_types,
        "error_events": error_events,
        "done_received": "done" in event_types,
        "metrics_received": "metrics" in event_types,
        "total_tokens": int(done_payload.get("total_tokens", 0) or 0),
        "workflow_runs": int(metrics_payload.get("run_count", 0)),
        "synthetic_session_deleted": cleanup_status == 204,
        "credentials_printed": False,
        "response_content_recorded": False,
    }


def run_regression_baseline(artifact_dir: Path, include_qwen: bool = True) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if not harden_private_path(artifact_dir, recursive=True):
        raise RuntimeError(f"could not restrict artifact directory ACL: {artifact_dir}")
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    git = shutil.which("git")
    checks: dict[str, Any] = {}
    checks["backend_unittest"] = run_logged_command(
        "backend_unittest",
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
        BACKEND_DIR,
        artifact_dir,
        timeout=600,
    )
    if npm:
        checks["frontend_lint"] = run_logged_command(
            "frontend_lint",
            [npm, "run", "lint"],
            REPOSITORY_DIR / "frontend",
            artifact_dir,
            timeout=300,
        )
        checks["frontend_build"] = run_logged_command(
            "frontend_build",
            [npm, "run", "build"],
            REPOSITORY_DIR / "frontend",
            artifact_dir,
            timeout=600,
        )
    else:
        checks["frontend_lint"] = {"success": False, "reason": "npm not found"}
        checks["frontend_build"] = {"success": False, "reason": "npm not found"}
    if git:
        checks["git_diff_check"] = run_logged_command(
            "git_diff_check",
            [git, "diff", "--check"],
            REPOSITORY_DIR,
            artifact_dir,
            timeout=120,
        )
    else:
        checks["git_diff_check"] = {"success": False, "reason": "git not found"}
    checks["qwen_sse"] = (
        asyncio.run(run_qwen_sse_smoke(artifact_dir))
        if include_qwen
        else {"success": False, "skipped": True}
    )
    return {
        "captured_at": utc_now(),
        "checks": checks,
        "success": all(bool(check.get("success")) for check in checks.values()),
    }


def render_markdown_report(results: dict[str, Any]) -> str:
    inspect_result = results.get("inspect", {})
    snapshot = inspect_result.get("snapshot", {})
    inventory = inspect_result.get("inventory", {})
    schema_differences = inspect_result.get("schema_differences", [])
    backup = results.get("backup", {})
    dependencies = results.get("dependencies", {})
    baseline = results.get("baseline", {})
    status = "通过" if results.get("success") else "未通过"
    lines = [
        "# KMS 开发前置门禁核验报告",
        "",
        f"> 核验时间：{results.get('captured_at', utc_now())}",
        f"> 总体结论：**{status}**",
        "> 范围：仅完成《KMS开发计划.md》第 5 节；未执行正式数据库迁移。",
        "",
        "## 1. MySQL 与结构差异",
        "",
    ]
    if snapshot:
        server = snapshot.get("server", {})
        lines.extend(
            [
                f"- 连接模式：`{snapshot.get('connection_mode')}`。",
                f"- 数据库版本：`{server.get('version')}`。",
                f"- 数据库字符集/排序规则：`{server.get('database_character_set')}` / `{server.get('database_collation')}`。",
                f"- 表数：{snapshot.get('totals', {}).get('table_count', 0)}；总行数：{snapshot.get('totals', {}).get('row_count', 0)}。",
            ]
        )
    if schema_differences:
        lines.append(f"- 发现 {len(schema_differences)} 项结构差异：")
        for difference in schema_differences:
            locator = ".".join(
                str(value)
                for value in (difference.get("table"), difference.get("column"))
                if value
            )
            detail = ""
            if "expected" in difference or "actual" in difference:
                detail = f"（期望 `{difference.get('expected')}`，实际 `{difference.get('actual')}`）"
            lines.append(
                f"  - `{difference.get('authority')}` / `{difference.get('kind')}` / `{locator}`{detail}"
            )
    else:
        lines.append("- 实际实例、SQLModel 与 `backend/init_db.sql` 未发现结构差异。")

    lines.extend(["", "## 2. 全量备份", ""])
    if backup:
        validation = backup.get("validation", {})
        lines.extend(
            [
                f"- 文件：`{backup.get('backup_path')}`。",
                f"- 大小：{validation.get('size_bytes', 0)} 字节；SHA-256：`{validation.get('sha256')}`。",
                f"- 可读性、dump 头和完成标记：{'通过' if validation.get('valid') else '失败'}。",
                "- 恢复命令已记录在 `backup_manifest.json`；按要求未在当前数据库执行恢复。",
            ]
        )
    else:
        lines.append("- 未生成备份。")

    lines.extend(["", "## 3. 旧知识库一致性", ""])
    if inventory:
        lines.extend(
            [
                f"- `documents.type=knowledge`：{inventory.get('database_knowledge_documents', 0)} 条。",
                f"- 可读文件/MD5 匹配：{inventory.get('existing_files', 0)} / {inventory.get('matching_file_md5', 0)}。",
                f"- Chroma / BM25 切片：{inventory.get('chroma', {}).get('chunks', 0)} / {inventory.get('bm25', {}).get('chunks', 0)}。",
                f"- MD5 重复组：{len(inventory.get('duplicate_md5_groups', []))}；异常项：{len(inventory.get('anomalies', []))}。",
                "- 逐文档路径、存储/实算 MD5、两类索引切片数见 `knowledge_inventory.json`；未记录论文正文。",
            ]
        )
    else:
        lines.append("- 未完成盘点。")

    lines.extend(["", "## 4. 新依赖真实兼容性", ""])
    for name, component in dependencies.get("components", {}).items():
        version = dependencies.get("versions", {}).get(name) or dependencies.get("versions", {}).get(name.capitalize())
        lines.append(
            f"- {name}: `{version or 'unknown'}`，{'通过' if component.get('success') else '失败'}。"
        )
        if name == "redis":
            lines.append(
                f"  - Redis 服务探测：`{component.get('server_status')}`；前置门禁只要求客户端兼容，迭代 B 前仍须提供 Redis 服务。"
            )
    lines.extend(
        [
            "",
            "Celery 使用隔离 `memory://` broker 启动 Windows 可用的 threads worker（`concurrency=2`）并真实取回任务结果；Whoosh 完成临时索引写入/查询；Alembic 完成临时数据库 upgrade/downgrade。",
            "",
            "## 5. 当前回归与真实问答基线",
            "",
        ]
    )
    for name, check in baseline.get("checks", {}).items():
        extra = ""
        if check.get("duration_seconds") is not None:
            extra = f"，{check['duration_seconds']} 秒"
        if name == "qwen_sse" and check.get("total_tokens") is not None:
            extra += f"，{check.get('total_tokens')} tokens"
        if check.get("reason"):
            extra += f"；原因：{check.get('reason')}"
        lines.append(f"- `{name}`：{'通过' if check.get('success') else '失败'}{extra}。")
    qwen_check = baseline.get("checks", {}).get("qwen_sse", {})
    if qwen_check.get("reason"):
        qwen_note = "本次未创建合成会话，也未发起外部模型请求。"
    else:
        qwen_note = "合成会话在核验结束后删除。"
    lines.extend(
        [
            "",
            "真实问答只记录事件类型、Token 数与清理状态，不记录回答内容或 API Key；" + qwen_note,
            "",
            "## 6. 结论与边界",
            "",
            f"- 前置门禁结论：**{status}**。",
            "- 当前操作未修改旧 `documents`、Chroma 集合或 BM25 索引，未执行 KMS 正式迁移，也未试恢复生产数据库。",
            "- Redis 服务端当前若为 `not_running`，不阻断本门禁的依赖兼容性结论，但会阻断迭代 B 的 Redis/Celery 真实集成门禁。",
            "- 详细机器证据位于被 Git 忽略的本次 artifact 目录和 backup 目录。",
            "",
        ]
    )
    return "\n".join(lines)


def run_inspection() -> dict[str, Any]:
    snapshot, knowledge_documents = asyncio.run(collect_database_snapshot())
    init_schema = parse_init_db_schema(
        (BACKEND_DIR / "init_db.sql").read_text(encoding="utf-8")
    )
    sqlmodel_schema = model_schema()
    differences = compare_schema(
        snapshot,
        init_schema,
        "init_db.sql",
        include_delete_rule=True,
    ) + compare_schema(snapshot, sqlmodel_schema, "SQLModel")
    inventory = collect_knowledge_inventory(knowledge_documents)
    return {
        "success": True,
        "snapshot": snapshot,
        "schema_authorities": {
            "init_db": init_schema,
            "sqlmodel": sqlmodel_schema,
        },
        "schema_differences": differences,
        "inventory": inventory,
    }


def _capture_step(name: str, callback: Any) -> dict[str, Any]:
    try:
        return callback()
    except Exception as exc:
        return {
            "success": False,
            "step": name,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def execute(args: argparse.Namespace) -> tuple[dict[str, Any], Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_dir = Path(args.artifact_dir).resolve() if args.artifact_dir else (
        BACKEND_DIR / ".artifacts" / "kms_preflight" / timestamp
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(args.backup_dir).resolve() if args.backup_dir else (
        BACKEND_DIR / "backups" / "kms_preflight"
    )
    results: dict[str, Any] = {"captured_at": utc_now(), "artifact_dir": str(artifact_dir)}

    if args.command in {"inspect", "all"}:
        results["inspect"] = _capture_step("inspect", run_inspection)
        inspect_result = results["inspect"]
        if inspect_result.get("snapshot"):
            write_json(artifact_dir / "database_snapshot.json", inspect_result["snapshot"])
            write_json(
                artifact_dir / "schema_comparison.json",
                {
                    "authorities": inspect_result["schema_authorities"],
                    "differences": inspect_result["schema_differences"],
                },
            )
            write_json(
                artifact_dir / "knowledge_inventory.json",
                inspect_result["inventory"],
            )
    if args.command in {"backup", "all"}:
        results["backup"] = _capture_step(
            "backup", lambda: create_database_backup(backup_dir)
        )
        if results["backup"].get("backup_path"):
            write_json(artifact_dir / "backup_manifest.json", results["backup"])
    if args.command in {"dependencies", "all"}:
        results["dependencies"] = _capture_step("dependencies", run_dependency_smoke)
        write_json(artifact_dir / "dependency_smoke.json", results["dependencies"])
    if args.command in {"baseline", "all"}:
        results["baseline"] = _capture_step(
            "baseline",
            lambda: run_regression_baseline(
                artifact_dir,
                include_qwen=not args.skip_qwen,
            ),
        )
        write_json(artifact_dir / "baseline.json", results["baseline"])

    step_names = [
        name for name in ("inspect", "backup", "dependencies", "baseline") if name in results
    ]
    results["success"] = bool(step_names) and all(
        bool(results[name].get("success")) for name in step_names
    )
    report_path = Path(args.report).resolve() if args.report else artifact_dir / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_markdown_report(results), encoding="utf-8")
    write_json(artifact_dir / "result.json", results)
    return results, report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the KMS development preflight gate")
    parser.add_argument(
        "command",
        choices=("inspect", "backup", "dependencies", "baseline", "all"),
        nargs="?",
        default="all",
    )
    parser.add_argument("--artifact-dir", help="Evidence directory (default: ignored timestamp directory)")
    parser.add_argument("--backup-dir", help="Logical backup directory")
    parser.add_argument("--report", help="Markdown report path")
    parser.add_argument(
        "--skip-qwen",
        action="store_true",
        help="Skip the real Qwen/SSE smoke (the full gate will fail)",
    )
    return parser


def main() -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    args = build_parser().parse_args()
    results, report_path = execute(args)
    summary = {
        "success": results["success"],
        "artifact_dir": results["artifact_dir"],
        "report": str(report_path),
        "steps": {
            name: bool(results[name].get("success"))
            for name in ("inspect", "backup", "dependencies", "baseline")
            if name in results
        },
    }
    # ASCII JSON avoids a known conda-run/GBK output encoding failure on Windows.
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if results["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
