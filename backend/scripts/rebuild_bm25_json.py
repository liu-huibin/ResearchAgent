"""One-way safe rebuild of the non-executable BM25 JSON index from Chroma."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.core.config import settings  # noqa: E402
from app.services.bm25_index import sync_from_chroma  # noqa: E402
from app.services.vectordb import get_collection  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    chroma_count = get_collection().count()
    if not args.apply:
        print(json.dumps({"apply": False, "chroma_chunks": chroma_count}))
        return 0

    indexed_count = sync_from_chroma("knowledge_base")
    json_path = Path(settings.bm25_persist_dir) / "knowledge_base.json"
    legacy_path = Path(settings.bm25_persist_dir) / "knowledge_base.pkl"
    success = indexed_count == chroma_count and json_path.is_file()
    print(
        json.dumps(
            {
                "success": success,
                "chroma_chunks": chroma_count,
                "bm25_json_chunks": indexed_count,
                "legacy_pickle_preserved": legacy_path.is_file(),
            }
        )
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
