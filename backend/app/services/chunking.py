from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings


def chunk_document(text: str, filename: str, doc_id: int) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ".", "!", "?", ";", ",", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_text(text)
    return [
        {
            "content": chunk,
            "metadata": {
                "document_id": doc_id,
                "filename": filename,
                "chunk_index": i,
                "total_chunks": len(chunks),
            },
        }
        for i, chunk in enumerate(chunks)
    ]
