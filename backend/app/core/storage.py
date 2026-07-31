"""Shared upload validation and local-file storage boundaries."""

import hashlib
import os
import uuid
from pathlib import Path

from app.core.config import settings

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx"}


class UploadValidationError(ValueError):
    """Raised when an uploaded file violates the public upload contract."""


def validate_upload_extension(
    filename: str | None,
    allowed_extensions: set[str] | None = None,
) -> str:
    extension = Path(filename or "").suffix.lower()
    allowed = allowed_extensions or ALLOWED_UPLOAD_EXTENSIONS
    if extension not in allowed:
        raise UploadValidationError(
            f"不支持的文件格式: {extension}，仅支持 PDF/Word"
        )
    return extension


def validate_upload_size(content: bytes, max_size_mb: int | None = None) -> float:
    limit_mb = max_size_mb or settings.max_upload_size_mb
    size_mb = len(content) / (1024 * 1024)
    if size_mb > limit_mb:
        raise UploadValidationError(f"文件大小超过限制 ({limit_mb}MB)")
    return size_mb


def compute_md5(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def store_upload(
    content: bytes,
    extension: str,
    *relative_parts: str,
) -> str:
    target_dir = Path(settings.upload_dir).joinpath(*relative_parts)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid.uuid4().hex}{extension}"
    target.write_bytes(content)
    return str(target)


def remove_file(file_path: str) -> None:
    try:
        Path(file_path).unlink(missing_ok=True)
    except OSError:
        raise


def remove_empty_session_directory(session_id: int, user_id: int = 1) -> None:
    """Remove only the expected empty session directory, never recursively."""
    sessions_root = os.path.realpath(
        os.path.abspath(os.path.join(settings.upload_dir, str(user_id), "sessions"))
    )
    session_dir = os.path.realpath(
        os.path.abspath(os.path.join(sessions_root, str(session_id)))
    )

    try:
        is_expected_child = (
            session_dir != sessions_root
            and os.path.commonpath([sessions_root, session_dir]) == sessions_root
        )
    except ValueError:
        is_expected_child = False

    if not is_expected_child:
        return

    try:
        os.rmdir(session_dir)
    except (FileNotFoundError, OSError):
        return
