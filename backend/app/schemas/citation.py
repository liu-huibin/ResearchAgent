from typing import Literal

from pydantic import BaseModel


class CitationFragment(BaseModel):
    unit: int
    unit_text: str
    start: int
    end: int
    text: str
    occurrence: int


class CitationResponse(BaseModel):
    document_id: int
    chunk_index: int
    filename: str
    file_type: Literal["pdf", "docx"]
    text: str
    status: Literal["exact", "ambiguous", "unavailable"]
    fragments: list[CitationFragment]
