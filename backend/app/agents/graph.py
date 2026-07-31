"""LangGraph topology for the ResearchMate multi-agent workflow."""

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    after_reader,
    after_review,
    finalize_node,
    ideation_node,
    reader_node,
    reviewer_node,
    revision_node,
    supervisor_node,
)
from app.agents.state import ResearchState


@lru_cache(maxsize=1)
def build_multi_agent_graph():
    graph = StateGraph(ResearchState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("reader", reader_node)
    graph.add_node("ideation", ideation_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("revision", revision_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "supervisor")
    graph.add_edge("supervisor", "reader")
    graph.add_conditional_edges(
        "reader",
        after_reader,
        {"ideation": "ideation", "reviewer": "reviewer", "finalize": "finalize"},
    )
    graph.add_edge("ideation", "reviewer")
    graph.add_conditional_edges(
        "reviewer",
        after_review,
        {"revision": "revision", "finalize": "finalize"},
    )
    graph.add_edge("revision", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()
