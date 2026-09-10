import io
import logging
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from unittest.mock import patch

from app.core.logging import ResilientTimedRotatingFileHandler


class ResilientLoggingTests(unittest.TestCase):
    def test_windows_sharing_violation_defers_rollover_and_keeps_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "researchmate.log"
            handler = ResilientTimedRotatingFileHandler(
                log_path,
                when="midnight",
                backupCount=30,
                encoding="utf-8",
            )
            error = PermissionError("file is in use")
            error.winerror = 32
            stderr = io.StringIO()
            try:
                handler.stream.close()
                handler.stream = None
                handler.rolloverAt = 0
                with (
                    patch.object(
                        TimedRotatingFileHandler,
                        "doRollover",
                        side_effect=error,
                    ),
                    redirect_stderr(stderr),
                ):
                    handler.emit(
                        logging.LogRecord(
                            "test",
                            logging.INFO,
                            __file__,
                            1,
                            "record persisted",
                            (),
                            None,
                        )
                    )
            finally:
                handler.close()

            self.assertGreater(handler.rolloverAt, int(time.time()))
            self.assertIn("record persisted", log_path.read_text(encoding="utf-8"))
            self.assertIn("rollover deferred", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_non_sharing_rollover_error_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            handler = ResilientTimedRotatingFileHandler(
                Path(temp_dir) / "researchmate.log",
                when="midnight",
                encoding="utf-8",
            )
            error = PermissionError("access denied")
            error.winerror = 5
            try:
                with patch.object(
                    TimedRotatingFileHandler,
                    "doRollover",
                    side_effect=error,
                ):
                    with self.assertRaises(PermissionError):
                        handler.doRollover()
            finally:
                handler.close()


if __name__ == "__main__":
    unittest.main()
