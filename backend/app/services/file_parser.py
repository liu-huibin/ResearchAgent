import logging
import os

logger = logging.getLogger(__name__)


def extract_text_from_file(file_path: str, max_chars: int | None = 20000) -> str:
    """Extract text from a PDF or Word file. Truncates to max_chars if set."""
    ext = os.path.splitext(file_path)[1].lower()
    logger.info("Extracting text: path=%s, ext=%s", file_path, ext)

    if ext == ".pdf":
        text = _extract_pdf(file_path)
    elif ext in (".doc", ".docx"):
        text = _extract_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    original_len = len(text)
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars] + "\n\n[文档内容过长，已截断...]"
    logger.info("Text extracted: %d chars (truncated from %d)", len(text), original_len)
    return text


def _extract_pdf(file_path: str) -> str:
    from PyPDF2 import PdfReader

    reader = PdfReader(file_path)
    parts = []
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            parts.append(page_text)
    return "\n\n".join(parts)


def _extract_docx(file_path: str) -> str:
    from docx import Document as DocxDocument

    doc = DocxDocument(file_path)
    parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    return "\n".join(parts)
