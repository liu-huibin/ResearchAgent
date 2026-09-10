from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class MessageCreate(BaseModel):
    content: str


class ToolExecutionSummary(BaseModel):
    kind: Literal["stage", "tool"] = "tool"
    agent: Optional[str] = None
    stage: Optional[str] = None
    detail: Optional[str] = Field(default=None, max_length=600)
    report: Optional[str] = Field(default=None, max_length=1600)
    tool: Optional[str] = None
    status: Literal["running", "succeeded", "failed"] = "succeeded"
    is_error: bool = False

    model_config = {"extra": "ignore"}


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: Optional[str] = None
    # Sanitized execution summaries only. Historical thought/tool payload
    # columns are deliberately excluded from every API response.
    tool_calls: Optional[list[ToolExecutionSummary]] = None
    created_at: datetime
