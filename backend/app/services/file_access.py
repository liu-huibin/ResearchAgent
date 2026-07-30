import os
from pathlib import Path

from app.services.file_parser import extract_text_from_file

ALLOWED_DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md"}


class FileAccessError(ValueError):
    """Raised when an MCP file request violates the configured policy."""


def resolve_document_path(file_path: str, document_root: str) -> Path:
    """Resolve a requested file and prove it remains inside document_root."""
    if not file_path or not file_path.strip():
        raise FileAccessError("文件路径不能为空")

    root = Path(document_root).expanduser().resolve()
    requested = Path(file_path).expanduser()
    candidate = requested if requested.is_absolute() else root / requested

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise FileAccessError("文件不存在") from exc

    try:
        inside_root = os.path.commonpath([str(root), str(resolved)]) == str(root)
    except ValueError:
        inside_root = False
    if not inside_root:
        raise FileAccessError("访问被拒绝：文件路径超出 MCP 文档根目录")
    if not resolved.is_file():
        raise FileAccessError("指定路径不是文件")
    if resolved.suffix.lower() not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise FileAccessError("不支持的文件格式")
    return resolved


def read_document_safely(file_path: str, document_root: str) -> str:
    """Read an allowed document without exposing broader filesystem access."""
    resolved = resolve_document_path(file_path, document_root)
    if resolved.suffix.lower() in {".txt", ".md"}:
        text = resolved.read_text(encoding="utf-8")
        if len(text) > 20000:
            return text[:20000] + "\n\n[文档内容过长，已截断...]"
        return text
    return extract_text_from_file(str(resolved))
