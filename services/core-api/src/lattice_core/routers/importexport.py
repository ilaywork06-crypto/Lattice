"""Excel import/export endpoints (§11)."""

import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_manager, require_viewer
from lattice_core.models import ItemTemplate, ItemType, User
from lattice_core.schemas import ImportResult
from lattice_core.services import importexport as svc

router = APIRouter(prefix="/data", tags=["import-export"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Browsers and OSes label .xlsx uploads inconsistently (or not at all), so the
# extension and the workbook's own content are what decide — not the MIME type.
_EXTENSIONS = (".xlsx", ".xlsm")


def _xlsx_response(content: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content),
        media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _name(db: Session, prefix: str, template_id: int | None, type: ItemType | None) -> str:
    if template_id:
        tpl = db.get(ItemTemplate, template_id)
        if tpl is None:
            raise HTTPException(status_code=404, detail="Template not found")
        return f"lattice_{prefix}_{tpl.type.value}_{tpl.serial_prefix}.xlsx"
    return f"lattice_{prefix}{f'_{type.value}' if type else ''}.xlsx"


@router.get("/template")
def download_template(
    template_id: int | None = Query(None),
    type: ItemType | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    """An import workbook: one sheet per template, headers = its creation fields."""
    content = svc.build_template(db, template_id, type)
    return _xlsx_response(content, _name(db, "import", template_id, type))


@router.get("/export")
def export(
    template_id: int | None = Query(None),
    type: ItemType | None = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    content = svc.export_items(db, template_id, type)
    return _xlsx_response(content, _name(db, "export", template_id, type))


@router.post("/import", response_model=ImportResult)
async def import_items(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    """All-or-nothing: any invalid cell → 400 listing every bad cell.

    Manager-only: an import creates items directly, and editors create items by
    proposal (§9) — letting them import was a way around the approval workflow.
    """
    if not file.filename or not file.filename.lower().endswith(_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Please upload an Excel .xlsx file")
    content = await file.read()
    return svc.import_items(db, content, user)

