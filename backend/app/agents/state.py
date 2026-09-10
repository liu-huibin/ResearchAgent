"""Types shared by the ResearchMate LangGraph workflow."""

import operator
from typing import Annotated, Literal, TypedDict

AgentName = Literal[
    "Supervisor",
    "ReaderAgent",
    "IdeationAgent",
    "ReviewerAgent",
]


class ResearchState(TypedDict, total=False):
    user_message: str
    document_text: str
    session_id: int
    trace_id: str
    prompt_variant: str
    prompt_version: str
    workflow: str
    reader_output: str
    reader_public_report: str
    ideation_output: str
    ideation_public_report: str
    review_output: str
    reviewer_public_report: str
    revision_output: str
    revision_public_report: str
    final_output: str
    citation_markers: Annotated[list[str], operator.add]
    iterations: Annotated[int, lambda current, update: current + update]


NODE_TO_AGENT: dict[str, AgentName] = {
    "supervisor": "Supervisor",
    "reader": "ReaderAgent",
    "ideation": "IdeationAgent",
    "reviewer": "ReviewerAgent",
    "revision": "IdeationAgent",
    "finalize": "Supervisor",
}
