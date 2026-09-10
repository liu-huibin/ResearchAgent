from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.document import DocumentResponse
from app.services.knowledge.service import (
    DuplicateKnowledgeError,
    EmptyDocumentError,
    KnowledgeNotFoundError,
    KnowledgeProcessingError,
    cleanup_failed_upload as _cleanup_failed_upload,
    list_knowledge as fetch_knowledge,
    remove_knowledge as delete_knowledge,
    upload_knowledge as ingest_knowledge,
)
from app.core.storage import (
    PreparedUpload,
    UploadValidationError,
    cleanup_prepared_upload,
    prepare_upload,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/upload", response_model=DocumentResponse)
async def upload_knowledge(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    prepared: PreparedUpload | None = None
    try:
        prepared = await prepare_upload(file)
        return await ingest_knowledge(db, prepared.filename, prepared)
    except (UploadValidationError, EmptyDocumentError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DuplicateKnowledgeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KnowledgeProcessingError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        cleanup_prepared_upload(prepared)


@router.delete("/{doc_id}", status_code=204)
async def remove_knowledge(
    doc_id: int,
    db: AsyncSession = Depends(get_session),
):
    try:
        await delete_knowledge(db, doc_id)
    except KnowledgeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/list", response_model=list[DocumentResponse])
async def list_knowledge(db: AsyncSession = Depends(get_session)):
    return await fetch_knowledge(db)
