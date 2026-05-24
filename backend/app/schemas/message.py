from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: Optional[str] = None
    thought: Optional[str] = None
    tool_calls: Optional[dict] = None
    created_at: datetime
