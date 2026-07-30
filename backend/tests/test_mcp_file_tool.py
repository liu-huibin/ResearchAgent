import tempfile
import unittest
from pathlib import Path

from app.services.mcp_client import MCPFileClient


class MCPFileToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_discovers_and_reads_file_inside_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "documents"
            root.mkdir()
            (root / "paper.txt").write_text(
                "ResearchMate MCP integration works.",
                encoding="utf-8",
            )
            client = MCPFileClient(str(root))
            try:
                await client.start()
                self.assertIn("read_file", await client.list_tools())
                content = await client.read_file("paper.txt")
            finally:
                await client.close()

            self.assertIn("MCP integration works", content)

    async def test_server_rejects_file_outside_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "documents"
            root.mkdir()
            outside = Path(temp_dir) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            client = MCPFileClient(str(root))
            try:
                result = await client.read_file(str(outside))
            finally:
                await client.close()

            self.assertIn("访问被拒绝", result)


if __name__ == "__main__":
    unittest.main()
