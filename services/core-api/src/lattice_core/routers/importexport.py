"""Excel import/export endpoints (§11)."""

import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_editor, require_viewer
from lattice_core.models import ItemType, User
from lattice_core.services import importexport as svc

router = APIRouter(prefix="/data", tags=["import-export"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content),
        media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/template")
def download_template(
    type: ItemType | None = None, _: User = Depends(require_viewer)
):
    content = svc.build_template(type)
    return _xlsx_response(content, "lattice_import_template.xlsx")


@router.get("/export")
def export(
    type: ItemType | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    content = svc.export_items(db, type)
    name = f"lattice_{type.value if type else 'items'}_export.xlsx"
    return _xlsx_response(content, name)


@router.post("/import")
async def import_items(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx file")
    content = await file.read()
    try:
        result = svc.import_items(db, content, user)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}")
    return result
