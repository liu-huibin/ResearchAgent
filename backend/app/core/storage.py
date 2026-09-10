"""Shared upload validation and local-file storage boundaries."""

import hashlib
import os
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.file_permissions import harden_private_path

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".docx"}
UPLOAD_CHUNK_SIZE = 1024 * 1024

_ALLOWED_MEDIA_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
}


class UploadValidationError(ValueError):
    """Raised when an uploaded file violates the public upload contract."""


@dataclass(frozen=True)
class PreparedUpload:
    filename: str
    extension: str
    temp_path: Path
    size_bytes: int
    file_md5: str

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


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
    if not harden_private_path(target_dir):
        raise UploadValidationError("无法建立私有文件存储目录")
    target = target_dir / f"{uuid.uuid4().hex}{extension}"
    target.write_bytes(content)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    harden_private_path(target)
    return str(target)


async def prepare_upload(file: UploadFile) -> PreparedUpload:
    """Stream an upload to a bounded temporary file and validate its structure."""
    extension = validate_upload_extension(file.filename)
    media_type = (file.content_type or "").lower().split(";", 1)[0].strip()
    if media_type and media_type not in _ALLOWED_MEDIA_TYPES[extension]:
        raise UploadValidationError("文件 MIME 类型与扩展名不匹配")

    incoming_dir = Path(settings.upload_dir) / ".incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    if not harden_private_path(incoming_dir):
        raise UploadValidationError("无法建立私有上传暂存目录")
    descriptor, raw_path = tempfile.mkstemp(prefix="upload_", suffix=extension, dir=incoming_dir)
    temp_path = Path(raw_path)
    digest = hashlib.md5()  # noqa: S324 - duplicate-file compatibility identifier
    size_bytes = 0
    max_bytes = settings.max_upload_size_mb * 1024 * 1024

    try:
        with os.fdopen(descriptor, "wb") as target:
            while True:
                block = await file.read(UPLOAD_CHUNK_SIZE)
                if not block:
                    break
                size_bytes += len(block)
                if size_bytes > max_bytes:
                    raise UploadValidationError(
                        f"文件大小超过限制 ({settings.max_upload_size_mb}MB)"
                    )
                digest.update(block)
                target.write(block)
            target.flush()
            os.fsync(target.fileno())

        if size_bytes == 0:
            raise UploadValidationError("上传文件为空")
        _validate_file_structure(temp_path, extension)
        try:
            temp_path.chmod(0o600)
        except OSError:
            pass
        return PreparedUpload(
            filename=file.filename or "unknown",
            extension=extension,
            temp_path=temp_path,
            size_bytes=size_bytes,
            file_md5=digest.hexdigest(),
        )
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def _validate_file_structure(path: Path, extension: str) -> None:
    if extension == ".pdf":
        with path.open("rb") as stream:
            header = stream.read(1024)
        if b"%PDF-" not in header:
            raise UploadValidationError("PDF 文件签名无效")
        return

    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > settings.max_docx_entries:
                raise UploadValidationError("DOCX 条目数量超过安全限制")
            names = {info.filename for info in infos}
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise UploadValidationError("DOCX OOXML 结构无效")

            total_uncompressed = 0
            for info in infos:
                normalized = info.filename.replace("\\", "/")
                parts = Path(normalized).parts
                if normalized.startswith("/") or ".." in parts:
                    raise UploadValidationError("DOCX 包含不安全的条目路径")
                if info.flag_bits & 0x1:
                    raise UploadValidationError("不支持加密 DOCX")
                total_uncompressed += info.file_size
                if total_uncompressed > settings.max_docx_uncompressed_mb * 1024 * 1024:
                    raise UploadValidationError("DOCX 解压大小超过安全限制")
                if info.file_size and not info.compress_size:
                    raise UploadValidationError("DOCX 压缩比例异常")
                if info.compress_size:
                    ratio = info.file_size / info.compress_size
                    if ratio > settings.max_docx_compression_ratio:
                        raise UploadValidationError("DOCX 压缩比例超过安全限制")
    except zipfile.BadZipFile as exc:
        raise UploadValidationError("DOCX ZIP 结构无效") from exc


def store_prepared_upload(prepared: PreparedUpload, *relative_parts: str) -> str:
    """Atomically move a validated upload from staging into managed storage."""
    target_dir = Path(settings.upload_dir).joinpath(*relative_parts)
    target_dir.mkdir(parents=True, exist_ok=True)
    if not harden_private_path(target_dir):
        raise UploadValidationError("无法建立私有文件存储目录")
    target = target_dir / f"{uuid.uuid4().hex}{prepared.extension}"
    os.replace(prepared.temp_path, target)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    harden_private_path(target)
    return str(target)


def cleanup_prepared_upload(prepared: PreparedUpload | None) -> None:
    if prepared is not None:
        prepared.temp_path.unlink(missing_ok=True)


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
