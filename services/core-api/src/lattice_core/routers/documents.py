"""Uploaded files: staging an upload, and downloading any document.

Downloads go through the API (not a public static path), so a file is exactly as
protected as the item it belongs to.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_editor, require_viewer
from lattice_core.models import Document, User
from lattice_core.schemas import DocumentOut
from lattice_core.services import files as files_svc

router = APIRouter(tags=["documents"])


@router.post("/uploads", response_model=DocumentOut, status_code=201)
async def stage_upload(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    """Upload a file before the item it belongs to exists.

    The returned id goes into a files field's value when the item is created
    (or proposed); unattached uploads are swept after two weeks.
    """
    files_svc.sweep_staged(db)
    doc = await files_svc.store_upload(db, file, user, name=name)
    db.commit()
    return doc


@router.get("/documents/{doc_id}/download")
def download(doc_id: int, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not doc.is_file:
        raise HTTPException(status_code=400, detail="This document is a link")
    path = files_svc.path_for(doc)
    if not path.exists():
        raise HTTPException(status_code=410, detail="The stored file is missing")
    return FileResponse(
        path,
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.original_filename or doc.name,
    )
