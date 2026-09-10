import asyncio
import logging
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.subprocess_env import safe_subprocess_env

logger = logging.getLogger(__name__)
DOCUMENT_ROOT_ENV = "RESEARCHMATE_MCP_DOCUMENT_ROOT"


class MCPFileClient:
    """Persistent stdio MCP client used by the LangGraph file tool."""

    def __init__(self, document_root: str | None = None):
        self._configured_root = document_root
        self._stack: AsyncExitStack | None = None
        self._session: Any = None
        self._lifecycle_lock = asyncio.Lock()
        self._call_lock = asyncio.Lock()

    @property
    def document_root(self) -> Path:
        backend_root = Path(__file__).resolve().parents[2]
        configured = Path(self._configured_root or settings.mcp_document_root).expanduser()
        if not configured.is_absolute():
            configured = backend_root / configured
        return configured.resolve()

    @property
    def started(self) -> bool:
        return self._session is not None

    async def start(self) -> None:
        if self.started:
            return
        async with self._lifecycle_lock:
            if self.started:
                return

            # Lazy imports let static tooling report a useful dependency error.
            try:
                from mcp import ClientSession, StdioServerParameters
                from mcp.client.stdio import stdio_client
            except ImportError as exc:
                raise RuntimeError(
                    "MCP 依赖未安装，请执行 pip install -r requirements.txt"
                ) from exc

            root = self.document_root
            root.mkdir(parents=True, exist_ok=True)
            backend_root = Path(__file__).resolve().parents[2]
            env = safe_subprocess_env(
                {
                    DOCUMENT_ROOT_ENV: str(root),
                    "PYTHONPATH": str(backend_root),
                }
            )
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "app.mcp_server"],
                env=env,
            )

            stack = AsyncExitStack()
            try:
                async with asyncio.timeout(settings.mcp_start_timeout_seconds):
                    read_stream, write_stream = await stack.enter_async_context(
                        stdio_client(params)
                    )
                    session = await stack.enter_async_context(
                        ClientSession(read_stream, write_stream)
                    )
                    await session.initialize()
                    tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                if "read_file" not in names:
                    raise RuntimeError("MCP Server 未注册 read_file 工具")
            except Exception:
                await stack.aclose()
                raise

            self._stack = stack
            self._session = session
            logger.info("MCP file client connected: root=%s tools=%s", root, sorted(names))

    async def close(self) -> None:
        async with self._lifecycle_lock:
            stack = self._stack
            self._stack = None
            self._session = None
            if stack is not None:
                await stack.aclose()
                logger.info("MCP file client closed")

    async def list_tools(self) -> list[str]:
        await self.start()
        tools = await self._session.list_tools()
        return [tool.name for tool in tools.tools]

    async def read_file(self, file_path: str) -> str:
        if not settings.mcp_enabled and self._configured_root is None:
            return "MCP 文件工具未启用"
        await self.start()
        async with self._call_lock:
            result = await self._session.call_tool(
                "read_file",
                arguments={"file_path": file_path},
            )
        texts = [
            item.text for item in result.content
            if getattr(item, "type", None) == "text" and getattr(item, "text", None)
        ]
        output = "\n".join(texts)
        if result.isError:
            logger.warning("MCP read_file failed")
            return f"读取文件失败: {output or 'MCP 工具调用失败'}"
        logger.info("MCP read_file success: chars=%d", len(output))
        return output


mcp_file_client = MCPFileClient()
