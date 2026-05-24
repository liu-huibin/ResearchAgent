from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Column, DateTime, func


class Document(SQLModel, table=True):
    __tablename__ = "documents"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(default=1, index=True)
    filename: str = Field(max_length=255)
    file_path: str = Field(max_length=500)
    file_md5: str = Field(max_length=32)
    type: str = Field(max_length=10)  # knowledge / session
    session_id: Optional[int] = Field(default=None, foreign_key="sessions.id")
    created_at: datetime = Field(
        sa_column=Column(DateTime, default=func.now(), nullable=False)
    )
