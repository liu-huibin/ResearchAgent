from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: int
    filename: str
    type: str
    session_id: Optional[int] = None
    created_at: datetime
