"""Start the ResearchMate backend reliably from the repository root."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
APP_ROOT = BACKEND_ROOT / "app"
APP_MODULE = "app.main:app"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the ResearchMate API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable automatic reload for a single-process smoke test",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reload_enabled = not args.no_reload

    # The application deliberately stores relative data paths under backend/.
    # Normalizing the cwd here prevents root-directory launches from loading a
    # wrong .env file or creating a second data/log tree at repository root.
    os.chdir(BACKEND_ROOT)
    sys.path.insert(0, str(BACKEND_ROOT))

    uvicorn.run(
        APP_MODULE,
        host=args.host,
        port=args.port,
        reload=reload_enabled,
        reload_dirs=[str(APP_ROOT)] if reload_enabled else None,
        reload_excludes=["*.pyc", "*/__pycache__/*"] if reload_enabled else None,
    )


if __name__ == "__main__":
    main()
