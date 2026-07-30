from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WorkflowRunResponse(BaseModel):
    id: int
    session_id: int
    assistant_message_id: int | None = None
    trace_id: str
    status: str
    prompt_variant: str
    prompt_version: str
    langsmith_enabled: bool
    input_tokens: int
    output_tokens: int
    total_tokens: int
    agent_usage: dict[str, Any] | None = None
    iterations: int
    tool_calls: int
    tool_failures: int
    duration_ms: int
    started_at: datetime
    completed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionMetricsResponse(BaseModel):
    session_id: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    run_count: int
    latest_run: WorkflowRunResponse | None = None
    runs: list[WorkflowRunResponse]
