"""Resolve indexed citations against the unchanged source, without reindexing."""

import hashlib
import unicodedata
from pathlib import Path

from app.core.config import settings
from app.core.storage import _validate_file_structure
from app.services.file_access import resolve_document_path


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text) if not c.isspace())


def read_units(path: Path) -> tuple[str, list[dict]]:
    if path.suffix.lower() == ".pdf":
        from PyPDF2 import PdfReader
        reader = PdfReader(str(path))
        if len(reader.pages) > settings.max_pdf_pages:
            raise ValueError("PDF 页数超过安全限制")
        kind = "pdf"
        source = ((i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages))
    else:
        from docx import Document
        kind = "docx"
        source = ((i + 1, p.text) for i, p in enumerate(Document(str(path)).paragraphs))
    units = []
    total = 0
    for index, text in source:
        units.append({"unit": index, "text": text})
        total += len(text)
        if total >= settings.max_extracted_chars:
            break
    return kind, units


def locate_chunk(units: list[dict], chunk: str, start_index: int | None = None,
                 separator: str = "\n") -> tuple[str, list[dict]]:
    normalized = [normalize(u["text"]) for u in units]
    source = "".join(normalized)
    needle = normalize(chunk)
    if not needle:
        return "unavailable", []
    start = source.find(needle)
    if start < 0:
        return "unavailable", []
    if source.find(needle, start + 1) >= 0:
        # New chunks carry an offset in the exact parser output. Historical
        # chunks without offsets must not silently select the first duplicate.
        original = separator.join(u["text"] for u in units if u["text"].strip())
        if start_index is None or start_index < 0 or original[start_index:start_index + len(chunk)] != chunk:
            return "ambiguous", []
        start = len(normalize(original[:start_index]))
    end = start + len(needle)
    fragments = []
    cursor = 0
    for i, (unit, text) in enumerate(zip(units, normalized)):
        left, right = max(start, cursor), min(end, cursor + len(text))
        if right > left:
            fragments.append({"unit": unit["unit"], "unit_text": unit["text"],
                              "start": left - cursor, "end": right - cursor,
                              "text": text[left - cursor:right - cursor],
                              "occurrence": sum(1 for prev in units[:i]
                                                if normalize(prev["text"]) == text)})
        cursor += len(text)
    return "exact", fragments


def resolve_citation(document, chunk_index: int) -> dict:
    from app.services.vectordb import get_collection
    if chunk_index < 0:
        raise LookupError("引用分块不存在")
    indexed = {}
    try:
        indexed = get_collection().get(ids=[f"doc_{document.id}_chunk_{chunk_index}"],
                                       include=["documents", "metadatas"])
    except Exception as exc:
        if document.type != "session":
            raise RuntimeError("引用索引暂时不可用") from exc

    has_indexed_chunk = bool(indexed.get("ids") and indexed.get("documents"))
    metadata = (indexed.get("metadatas") or [{}])[0] or {}
    if has_indexed_chunk:
        try:
            indexed_document_id = int(metadata.get("document_id"))
            indexed_chunk_index = int(metadata.get("chunk_index"))
        except (TypeError, ValueError):
            raise LookupError("引用分块元数据无效") from None
        if indexed_document_id != document.id or indexed_chunk_index != chunk_index:
            raise LookupError("引用分块不匹配")
    elif document.type != "session":
        raise LookupError("引用分块已删除或不存在")

    root = Path(settings.upload_dir).resolve()
    # Stored relative paths are backend-relative, not upload-root-relative.
    path = resolve_document_path(str(Path(document.file_path).resolve()), str(root))
    if path.suffix.lower() not in {".pdf", ".docx"}:
        raise ValueError("不支持的引用文件格式")
    if path.stat().st_size > settings.max_upload_size_mb * 1024 * 1024:
        raise ValueError("源文件超过安全限制")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "md5").hexdigest()
    if digest != document.file_md5:
        raise ValueError("源文件已变化，无法验证旧引用；请重新入库")
    _validate_file_structure(path, path.suffix.lower())

    if has_indexed_chunk:
        chunk = indexed["documents"][0]
    else:
        from app.services.chunking import chunk_document
        from app.services.file_parser import extract_text_from_file

        document_text = extract_text_from_file(str(path))
        chunks = chunk_document(document_text, document.filename, document.id)
        if chunk_index >= len(chunks):
            raise LookupError("引用分块已删除或不存在")
        generated = chunks[chunk_index]
        chunk = generated["content"]
        metadata = generated["metadata"]

    kind, units = read_units(path)
    start_index = metadata.get("start_index")
    try:
        start_index = int(start_index) if start_index is not None else None
    except (TypeError, ValueError):
        start_index = None
    status, fragments = locate_chunk(units, chunk, start_index,
                                     "\n\n" if kind == "pdf" else "\n")
    return {"document_id": document.id, "chunk_index": chunk_index,
            "filename": document.filename, "file_type": kind, "text": chunk,
            "status": status, "fragments": fragments}
