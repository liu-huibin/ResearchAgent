import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.routers.sessions import _remove_empty_session_directory


class SessionDirectoryCleanupTests(unittest.TestCase):
    def test_empty_expected_session_directory_is_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_root = Path(temp_dir) / "uploads"
            session_dir = upload_root / "1" / "sessions" / "42"
            session_dir.mkdir(parents=True)

            with patch.object(settings, "upload_dir", str(upload_root)):
                _remove_empty_session_directory(42)

            self.assertFalse(session_dir.exists())

    def test_non_empty_session_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_root = Path(temp_dir) / "uploads"
            session_dir = upload_root / "1" / "sessions" / "43"
            session_dir.mkdir(parents=True)
            marker = session_dir / "untracked.txt"
            marker.write_text("preserve", encoding="utf-8")

            with patch.object(settings, "upload_dir", str(upload_root)):
                _remove_empty_session_directory(43)

            self.assertTrue(session_dir.is_dir())
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")


if __name__ == "__main__":
    unittest.main()
