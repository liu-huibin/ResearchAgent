"""ResearchMate MCP stdio server exposing a read-only document tool."""

import logging
import os

from mcp.server.fastmcp import FastMCP

from app.services.file_access import read_document_safely

logger = logging.getLogger(__name__)

DOCUMENT_ROOT_ENV = "RESEARCHMATE_MCP_DOCUMENT_ROOT"
mcp = FastMCP(
    "researchmate-files",
    instructions="Read-only access to academic documents under the configured root.",
)


@mcp.tool()
def read_file(file_path: str) -> str:
    """Read text from a PDF, Word, Markdown, or text file under the MCP root."""
    document_root = os.environ.get(DOCUMENT_ROOT_ENV, "data/documents")
    logger.info("MCP read_file request received")
    return read_document_safely(file_path, document_root)


def main() -> None:
    # stdio is reserved for MCP protocol messages; operational logs go to stderr.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
