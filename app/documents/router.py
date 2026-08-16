"""Sprint 016 (docs/DECISIONS.md ADR-032). No require_role — any
authenticated tenant user may upload/list/download, matching the
customer/project/portal-link creation precedent (routine work, not a
tenant-control decision).
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.database.models import User
from app.documents.models import DocumentOut
from app.documents.service import (
    CustomerNotFoundError,
    DisallowedFileTypeError,
    DocumentNotFoundError,
    FileTooLargeError,
    document_service,
)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    customer_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return document_service.upload_document(
            db,
            tenant_id=current_user.tenant_id,
            uploaded_by_user_id=current_user.id,
            customer_id=customer_id,
            file=file,
        )
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    except FileTooLargeError:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 20MB limit",
        )
    except DisallowedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{exc.extension}' is not allowed",
        )


@router.get("", response_model=list[DocumentOut])
def list_documents(
    customer_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return document_service.list_documents(db, current_user.tenant_id, customer_id=customer_id)


@router.get("/{document_id}/download")
def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = document_service.get_document(db, current_user.tenant_id, document_id)
    except DocumentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return FileResponse(
        path=document_service.file_path(row),
        media_type=row.content_type,
        filename=row.original_filename,
    )
