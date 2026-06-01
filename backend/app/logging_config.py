import logging
import os
from logging.handlers import TimedRotatingFileHandler

from app.config import settings

_logging_initialized = False


def setup_logging():
    global _logging_initialized
    if _logging_initialized:
        return
    _logging_initialized = True

    log_dir = settings.log_dir
    os.makedirs(log_dir, exist_ok=True)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    file_handler = TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "researchmate.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    for noisy in ("chromadb", "urllib3", "httpx", "openai", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
