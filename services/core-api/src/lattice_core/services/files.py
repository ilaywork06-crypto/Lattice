"""Uploaded files: stored on disk, recorded in ``documents``, served via the API.

The stored name is a random key, never the user's file name, so an upload can't
choose where it lands or overwrite another one. The original name and type are
kept on the row for the download.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from lattice_core.config import get_settings
from lattice_core.errors import DomainError
from lattice_core.models import Document, User

# Staged uploads (not yet attached to an item) older than this are removed.
STAGED_TTL = timedelta(days=14)
_CHUNK = 1024 * 1024


def upload_root() -> Path:
    root = Path(get_settings().upload_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def path_for(doc: Document) -> Path:
    if not doc.storage_key:
        raise DomainError("This document is a link, not an uploaded file")
    return upload_root() / doc.storage_key


async def store_upload(
    db: Session,
    upload: UploadFile,
    user: User,
    *,
    name: str | None = None,
    doc_type: str | None = None,
    item_id: int | None = None,
    template_id: int | None = None,
    field_id: int | None = None,
) -> Document:
    limit = get_settings().max_upload_mb * 1024 * 1024
    original = Path(upload.filename or "file").name[:255]
    key = f"{secrets.token_hex(16)}{Path(original).suffix[:16].lower()}"
    target = upload_root() / key
    size = 0
    try:
        with target.open("wb") as fh:
            while chunk := await upload.read(_CHUNK):
                size += len(chunk)
                if size > limit:
                    raise DomainError(
                        f"'{original}' is larger than the {get_settings().max_upload_mb} MB limit"
                    )
                fh.write(chunk)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    doc = Document(
        item_id=item_id,
        template_id=template_id,
        field_id=field_id,
        name=(name or original).strip() or original,
        doc_type=doc_type,
        storage_key=key,
        original_filename=original,
        content_type=upload.content_type or "application/octet-stream",
        size_bytes=size,
        uploaded_by=user.id,
    )
    db.add(doc)
    db.flush()
    return doc


def delete_document(db: Session, doc: Document) -> None:
    if doc.storage_key:
        (upload_root() / doc.storage_key).unlink(missing_ok=True)
    db.delete(doc)


def sweep_staged(db: Session) -> int:
    """Drop staged uploads nobody attached within the TTL."""
    cutoff = datetime.now(UTC) - STAGED_TTL
    stale = (
        db.query(Document)
        .filter(
            Document.item_id.is_(None),
            Document.template_id.is_(None),
            Document.created_at < cutoff,
        )
        .all()
    )
    for doc in stale:
        delete_document(db, doc)
    return len(stale)
