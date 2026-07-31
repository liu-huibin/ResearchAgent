# ResearchMate

ResearchMate is a FastAPI and React research assistant with session documents,
hybrid retrieval, a LangGraph multi-agent workflow, MCP file access, SSE
streaming, and local workflow metrics.

## Start from the repository root

Use the existing `ResearchAgent` Conda environment:

```powershell
conda run -n ResearchAgent python run_backend.py
conda run -n ResearchAgent python run_frontend.py
```

The backend listens on `127.0.0.1:8000`. The frontend listens on
`127.0.0.1:3000` and proxies `/api` to the backend. Both launchers fail if their
requested port is already occupied instead of silently selecting another port.

To use a different backend port, keep both launchers synchronized:

```powershell
conda run -n ResearchAgent python run_backend.py --port 8100
conda run -n ResearchAgent python run_frontend.py --backend-url http://127.0.0.1:8100
```

Use `run_backend.py --no-reload` for a single-process backend smoke test.

## Verification

```powershell
cd backend
conda run -n ResearchAgent python -B -m unittest discover -s tests -v

cd ../frontend
npm.cmd run lint
npm.cmd run build

cd ..
git diff --check
```

See [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md) for package boundaries
and dependency rules.
