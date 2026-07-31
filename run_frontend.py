"""Start the ResearchMate frontend reliably from the repository root."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the ResearchMate frontend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument(
        "--backend-url",
        default="http://127.0.0.1:8000",
        help="Backend origin used by the Vite /api proxy",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    npm_name = "npm.cmd" if os.name == "nt" else "npm"
    npm = shutil.which(npm_name)
    if npm is None:
        raise RuntimeError(f"{npm_name} was not found on PATH")

    env = os.environ.copy()
    env["VITE_BACKEND_URL"] = args.backend_url.rstrip("/")

    try:
        return subprocess.call(
            [
                npm,
                "run",
                "dev",
                "--",
                "--host",
                args.host,
                "--port",
                str(args.port),
                "--strictPort",
            ],
            cwd=FRONTEND_ROOT,
            env=env,
        )
    except KeyboardInterrupt:
        # Ctrl+C is a normal developer shutdown, not a startup failure.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
