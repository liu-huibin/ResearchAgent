import tempfile
import unittest
from pathlib import Path

from app.services.file_access import FileAccessError, read_document_safely


class ReadFileSecurityTests(unittest.TestCase):
    def test_similarly_named_sibling_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            allowed_base = Path(temp_dir) / "documents"
            sibling_base = Path(temp_dir) / "documents_outside"
            allowed_base.mkdir()
            sibling_base.mkdir()
            sibling_file = sibling_base / "paper.txt"
            sibling_file.write_text("outside", encoding="utf-8")

            with self.assertRaisesRegex(FileAccessError, "访问被拒绝"):
                read_document_safely(str(sibling_file), str(allowed_base))

    def test_relative_text_file_inside_root_is_read(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "documents"
            root.mkdir()
            paper = root / "paper.txt"
            paper.write_text("MCP 文件读取成功", encoding="utf-8")

            self.assertEqual(
                read_document_safely("paper.txt", str(root)),
                "MCP 文件读取成功",
            )


if __name__ == "__main__":
    unittest.main()
