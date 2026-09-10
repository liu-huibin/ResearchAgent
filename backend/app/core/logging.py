import logging
import os
import sys
import time
from logging.handlers import TimedRotatingFileHandler

from app.core.config import settings
from app.core.file_permissions import harden_private_path

_logging_initialized = False


class ResilientTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Keep logging when Windows temporarily locks the rollover source file."""

    _WINDOWS_SHARING_ERRORS = {32, 33}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rollover_deferred_reported = False

    def doRollover(self):  # noqa: N802 - logging handler API
        current_time = int(time.time())
        try:
            super().doRollover()
        except OSError as exc:
            if getattr(exc, "winerror", None) not in self._WINDOWS_SHARING_ERRORS:
                raise

            # TimedRotatingFileHandler closes its own stream before renaming.
            # A reload sibling, log viewer, or antivirus process can still hold
            # the file on Windows. Reopen it and defer rotation so subsequent
            # records continue to be persisted without one traceback per log.
            if not self.delay and self.stream is None:
                self.stream = self._open()
            self.rolloverAt = self.computeRollover(current_time)
            if not self._rollover_deferred_reported:
                sys.stderr.write(
                    "ResearchMate log rollover deferred because the active log "
                    "file is in use; logging will continue in the current file.\n"
                )
                self._rollover_deferred_reported = True
            return

        # Python 3.12 returns early when the destination archive already
        # exists, leaving rolloverAt expired and checking again on every emit.
        if self.rolloverAt <= current_time:
            self.rolloverAt = self.computeRollover(current_time)
        self._rollover_deferred_reported = False


def setup_logging():
    global _logging_initialized
    if _logging_initialized:
        return

    log_dir = settings.log_dir
    os.makedirs(log_dir, exist_ok=True)
    if not harden_private_path(log_dir):
        raise PermissionError(f"Could not restrict log directory permissions: {log_dir}")

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    file_handler = ResilientTimedRotatingFileHandler(
        filename=os.path.join(log_dir, "researchmate.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    harden_private_path(os.path.join(log_dir, "researchmate.log"))

    for noisy in (
        "chromadb",
        "urllib3",
        "httpx",
        "openai",
        "httpcore",
        "asyncio",
        # Uvicorn's reload watcher reports every cache/log/data write as an
        # INFO-level "changes detected" message. Actual reload failures still
        # surface through the uvicorn error logger.
        "watchfiles",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _logging_initialized = True
