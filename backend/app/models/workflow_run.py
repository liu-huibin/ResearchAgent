from datetime import datetime
from typing import Optional

from sqlmodel import Boolean, Column, DateTime, Field, JSON, SQLModel, func


class WorkflowRun(SQLModel, table=True):
    """Persisted Phase 5 metrics for one user-to-assistant workflow."""

    __tablename__ = "workflow_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="sessions.id", index=True)
    assistant_message_id: Optional[int] = Field(default=None, index=True)
    trace_id: str = Field(max_length=36, unique=True, index=True)
    status: str = Field(default="completed", max_length=30)
    prompt_variant: str = Field(default="phase4-v1", max_length=80)
    prompt_version: str = Field(default="", max_length=80)
    langsmith_enabled: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, default=False),
    )
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    agent_usage: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    iterations: int = Field(default=0)
    tool_calls: int = Field(default=0)
    tool_failures: int = Field(default=0)
    duration_ms: int = Field(default=0)
    started_at: datetime = Field(
        sa_column=Column(DateTime, default=func.now(), nullable=False)
    )
    completed_at: datetime = Field(
        sa_column=Column(DateTime, default=func.now(), nullable=False)
    )
