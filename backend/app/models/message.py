from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Column, JSON, DateTime, Text, func


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="sessions.id", index=True)
    role: str = Field(max_length=20)  # user / assistant / tool
    content: Optional[str] = Field(default=None, sa_column=Column(Text))
    thought: Optional[str] = Field(default=None, sa_column=Column(Text))
    tool_calls: Optional[list] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(
        sa_column=Column(DateTime, default=func.now(), nullable=False)
    )
