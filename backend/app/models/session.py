from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Column, DateTime, func


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(default=1, index=True)
    title: str = Field(default="新会话", max_length=100)
    active_document_id: Optional[int] = Field(default=None, foreign_key="documents.id")
    created_at: datetime = Field(
        sa_column=Column(DateTime, default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    )
