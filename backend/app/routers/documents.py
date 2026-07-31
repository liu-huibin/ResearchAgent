import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.document import DocumentResponse
from app.services.documents.service import (
    DocumentNotFoundError,
    SessionNotFoundError,
    get_document,
    get_session_document as find_session_document,
    upload_session_document as save_session_document,
)
from app.core.storage import (
    UploadValidationError,
    compute_md5,
    validate_upload_extension,
)

router = APIRouter(prefix="/api", tags=["documents"])


@router.post("/sessions/{session_id}/upload", response_model=DocumentResponse)
async def upload_session_document(
    session_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    try:
        validate_upload_extension(file.filename)
        content = await file.read()
        return await save_session_document(db, session_id, file.filename, content)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/document", response_model=DocumentResponse | None)
async def get_session_document(
    session_id: int,
    db: AsyncSession = Depends(get_session),
):
    return await find_session_document(db, session_id)


@router.get("/documents/{document_id}/file")
async def serve_document_file(
    document_id: int,
    db: AsyncSession = Depends(get_session),
):
    try:
        document = await get_document(db, document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not os.path.exists(document.file_path):
        raise HTTPException(status_code=404, detail="文件不存在")

    media_type = "application/pdf"
    if document.filename.endswith((".doc", ".docx")):
        media_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    return FileResponse(
        document.file_path,
        media_type=media_type,
        filename=document.filename,
    )
