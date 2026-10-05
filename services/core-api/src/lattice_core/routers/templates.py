"""Templates: the blueprints items are created from.

Everyone reads them (every list page groups by template); managers create and
edit them directly; editors propose template changes through /change-requests.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from lattice_core.database import get_db
from lattice_core.deps import require_manager, require_viewer
from lattice_core.models import (
    CardType,
    Document,
    FieldMode,
    FieldType,
    ItemTemplate,
    ItemType,
    TemplateField,
    User,
)
from lattice_core.schemas import (
    DocumentOut,
    TemplateCreate,
    TemplateOut,
    TemplateSummary,
    TemplateUpdate,
)
from lattice_core.services import files as files_svc
from lattice_core.services import templates as svc
from lattice_core.services import views

router = APIRouter(prefix="/templates", tags=["templates"])


def _get(db: Session, template_id: int) -> ItemTemplate:
    tpl = db.get(ItemTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl


@router.get("", response_model=list[TemplateSummary])
def list_templates(
    type: ItemType | None = None,
    card_type: CardType | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    """Every template with its unit counts per state (destroyed excluded)."""
    q = db.query(ItemTemplate).options(
        selectinload(ItemTemplate.fields),
        selectinload(ItemTemplate.child_templates),
        selectinload(ItemTemplate.parent_templates),
    )
    if type:
        q = q.filter(ItemTemplate.type == type)
    if card_type:
        q = q.filter(ItemTemplate.card_type == card_type)
    if search:
        like = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace(
            "_", "\\_"
        ) + "%"
        q = q.filter(
            or_(
                ItemTemplate.name.ilike(like, escape="\\"),
                ItemTemplate.serial_prefix.ilike(like, escape="\\"),
            )
        )
    templates = q.order_by(ItemTemplate.type, func.lower(ItemTemplate.name)).all()
    counts = views.template_counts(db, [t.id for t in templates])
    return [views.template_summary(t, counts.get(t.id)) for t in templates]


@router.get("/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: int, db: Session = Depends(get_db), _: User = Depends(require_viewer)
):
    return views.template_out(db, _get(db, template_id))


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(
    body: TemplateCreate, db: Session = Depends(get_db), user: User = Depends(require_manager)
):
    tpl = svc.create_template(db, body.model_dump(mode="json"), user)
    db.commit()
    return views.template_out(db, tpl)


@router.patch("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int,
    body: TemplateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    tpl = _get(db, template_id)
    svc.update_template(db, tpl, body.model_dump(mode="json", exclude_unset=True), user)
    db.commit()
    db.refresh(tpl)
    return views.template_out(db, tpl)


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager)
):
    svc.delete_template(db, _get(db, template_id), user)
    db.commit()


# ───────────── files shared by every item (a fixed "files" field) ─────────────
@router.post(
    "/{template_id}/fields/{field_id}/files", response_model=DocumentOut, status_code=201
)
async def upload_template_file(
    template_id: int,
    field_id: int,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    tpl = _get(db, template_id)
    field = db.get(TemplateField, field_id)
    if field is None or field.template_id != tpl.id:
        raise HTTPException(status_code=404, detail="Field not found")
    if field.field_type != FieldType.files or field.mode != FieldMode.fixed:
        raise HTTPException(
            status_code=400,
            detail="Only a files field set on the template holds template files",
        )
    doc = await files_svc.store_upload(
        db, file, user, name=name, template_id=tpl.id, field_id=field.id
    )
    db.commit()
    return doc


@router.delete("/{template_id}/files/{doc_id}", status_code=204)
def delete_template_file(
    template_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    doc = db.get(Document, doc_id)
    if doc is None or doc.template_id != template_id:
        raise HTTPException(status_code=404, detail="File not found")
    files_svc.delete_document(db, doc)
    db.commit()
