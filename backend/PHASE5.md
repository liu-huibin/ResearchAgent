# Phase 5: MCP and observability

## Runtime configuration

The defaults keep all existing chat features available and enable the local MCP
stdio server. Relative paths are resolved from `backend/`.

```dotenv
MCP_ENABLED=true
MCP_DOCUMENT_ROOT=data/documents

LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=researchmate
LANGSMITH_ENDPOINT=https://api.smith.langchain.com

PROMPT_PRIMARY_VARIANT=phase4-v1
PROMPT_EXPERIMENT_VARIANT=phase5-concise-v1
PROMPT_EXPERIMENT_PERCENTAGE=0
```

Set `LANGSMITH_TRACING=true` and provide a key to send the complete LangGraph,
agent, LLM, and tool-call hierarchy to LangSmith. If LangSmith is unavailable,
the workflow continues with local logs and database metrics.

`PROMPT_EXPERIMENT_PERCENTAGE` accepts `0` to `100`. Assignment is a stable
hash of the session ID, so the same session remains in the same experiment arm.
Prompt bundles and version identifiers live in `app/prompts/registry.py`.

## Metrics

Every completed, timed-out, errored, or client-cancelled workflow is stored in
`workflow_runs`. `GET /api/sessions/{session_id}/metrics` returns the latest 20
runs plus session token totals. The chat header displays latest-run and session
token usage. Loop count, tool failures, and slow workflows also emit warning
logs when configured thresholds are crossed.

## Verification

```powershell
conda run -n ResearchAgent python -m unittest discover -s tests -v
npm.cmd run lint
npm.cmd run build
```

The MCP integration tests launch the real stdio server, discover `read_file`,
read an allowed document, and verify that an outside path is rejected.
