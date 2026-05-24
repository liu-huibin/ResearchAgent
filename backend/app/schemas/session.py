from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = Field(default="新会话", max_length=100)


class SessionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=100)
    active_document_id: Optional[int] = None


class SessionResponse(BaseModel):
    id: int
    user_id: int
    title: str
    active_document_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class SessionListItem(BaseModel):
    id: int
    title: str
    active_document_id: Optional[int] = None
    updated_at: datetime
