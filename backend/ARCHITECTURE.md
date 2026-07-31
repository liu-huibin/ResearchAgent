# Backend architecture

The backend uses behavior-preserving layers. HTTP routes keep protocol concerns
small, application services own use-case orchestration, and infrastructure
adapters remain replaceable behind those services.

## Package responsibilities

```text
app/
├── core/                 configuration, database, logging, local storage
├── agents/               state, factories, nodes, graph topology, runner
├── routers/              FastAPI request/response and error mapping only
├── services/
│   ├── chat/             chat preparation, SSE translation, persistence
│   ├── documents/        session-document application service
│   ├── knowledge/        knowledge ingestion and deletion orchestration
│   ├── sessions/         session lifecycle orchestration
│   └── *.py              stable retrieval, MCP, LLM, and observability adapters
├── models/               SQLModel table definitions
├── schemas/              public API payloads
└── tools/                LangChain tool adapters
```

Configuration, database, and logging imports come from `app.core`. Agent code
imports directly from `app.agents`; the project does not maintain legacy Python
import facades because the frontend and backend are developed together.

## Dependency rules

1. Routers may import services, schemas, and core dependencies. They should not
   implement transactions, file writes, indexing, or SSE event state machines.
2. Services may import models and infrastructure adapters. They must not raise
   FastAPI-specific exceptions.
3. Core modules must not import routers or application services.
4. Agent nodes contain model-facing behavior; graph topology contains only
   routing; the runner owns limits, event translation, and workflow metrics.
5. Database, file, Chroma, and lexical-index changes require explicit rollback
   or compensating cleanup tests.
6. Do not add generic `utils.py`, `common.py`, or base-service abstractions
   without at least two concrete consumers and a stable shared contract.

## Required verification

Start both applications from the repository root:

```powershell
conda run -n ResearchAgent python run_backend.py
conda run -n ResearchAgent python run_frontend.py
```

When the backend uses a non-default port, pass the matching proxy target to the
frontend launcher, for example `run_backend.py --port 8100` together with
`run_frontend.py --backend-url http://127.0.0.1:8100`.

Run from `backend/`:

```powershell
conda run -n ResearchAgent python -B -m unittest discover -s tests -v
```

Run from `frontend/`:

```powershell
npm.cmd run lint
npm.cmd run build
```

Before delivery, run `git diff --check` from the repository root. Tests that
exercise external indexes or files must use temporary paths and must not delete
or rewrite historical data under `backend/data/`.
