import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings

logger = logging.getLogger(__name__)


def chunk_document(text: str, filename: str, doc_id: int) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ".", "!", "?", ";", ",", " ", ""],
        length_function=len,
        add_start_index=True,
    )
    chunks = splitter.create_documents([text])
    logger.info("Chunking: doc_id=%d, text_len=%d, chunks=%d", doc_id, len(text), len(chunks))
    return [
        {
            "content": chunk.page_content,
            "metadata": {
                "document_id": doc_id,
                "filename": filename,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "start_index": chunk.metadata["start_index"],
            },
        }
        for i, chunk in enumerate(chunks)
    ]
