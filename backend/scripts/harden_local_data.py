"""Apply private ACLs to existing ResearchMate local data and evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.file_permissions import harden_private_path  # noqa: E402


PRIVATE_PATHS = (
    "backups",
    ".artifacts",
    "data/bm25",
    "data/chroma",
    "data/documents",
    "data/uploads",
    "log",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps({"apply": False, "paths": list(PRIVATE_PATHS)}))
        return 0

    results = {}
    for relative in PRIVATE_PATHS:
        path = BACKEND_DIR / relative
        results[relative] = not path.exists() or harden_private_path(path, recursive=True)
    success = all(results.values())
    print(json.dumps({"success": success, "paths": results}))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
