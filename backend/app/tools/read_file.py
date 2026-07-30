from langchain_core.tools import tool

from app.services.mcp_client import mcp_file_client


@tool
async def read_file(file_path: str) -> str:
    """Read a document through the ResearchMate MCP Server.

    Args:
        file_path: A path under the configured MCP document root.

    Returns:
        The extracted text content from the file.
    """
    return await mcp_file_client.read_file(file_path)
