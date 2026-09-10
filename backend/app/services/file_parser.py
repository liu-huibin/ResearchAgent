import logging
import os

from app.core.config import settings

logger = logging.getLogger(__name__)


def extract_text_from_file(file_path: str, max_chars: int | None = 20000) -> str:
    """Extract text from a PDF or Word file. Truncates to max_chars if set."""
    ext = os.path.splitext(file_path)[1].lower()
    logger.info("Extracting text: ext=%s", ext)

    if ext == ".pdf":
        text = _extract_pdf(file_path, max_chars)
    elif ext == ".docx":
        text = _extract_docx(file_path, max_chars)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    original_len = len(text)
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars] + "\n\n[文档内容过长，已截断...]"
    logger.info("Text extracted: %d chars (truncated from %d)", len(text), original_len)
    return text


def _extract_pdf(file_path: str, max_chars: int | None) -> str:
    from PyPDF2 import PdfReader

    reader = PdfReader(file_path)
    if len(reader.pages) > settings.max_pdf_pages:
        raise ValueError(
            f"PDF page count exceeds safety limit ({settings.max_pdf_pages})"
        )
    parts = []
    total_chars = 0
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            parts.append(page_text)
            total_chars += len(page_text)
            if max_chars is not None and total_chars >= max_chars:
                break
    return "\n\n".join(parts)


def _extract_docx(file_path: str, max_chars: int | None) -> str:
    from docx import Document as DocxDocument

    doc = DocxDocument(file_path)
    parts = []
    total_chars = 0
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
            total_chars += len(para.text)
            if max_chars is not None and total_chars >= max_chars:
                break
    return "\n".join(parts)
