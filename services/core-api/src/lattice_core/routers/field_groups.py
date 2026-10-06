"""Field groups — reusable sets of field definitions for the template editor.

Everyone who can read templates can read groups; only managers write them
(they shape templates, which managers own).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from lattice_core.database import get_db
from lattice_core.deps import require_manager, require_viewer
from lattice_core.models import FieldGroup, FieldGroupField, User
from lattice_core.schemas import (
    FieldGroupCreate,
    FieldGroupFieldOut,
    FieldGroupOut,
    FieldGroupUpdate,
)
from lattice_core.services import field_groups as svc
from lattice_core.services import views

router = APIRouter(prefix="/field-groups", tags=["field-groups"])


def _get(db: Session, group_id: int) -> FieldGroup:
    group = db.get(FieldGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Field group not found")
    return group


def _out(db: Session, g: FieldGroup) -> FieldGroupOut:
    return FieldGroupOut(
        id=g.id,
        name=g.name,
        description=g.description,
        fields=[
            FieldGroupFieldOut(
                key=f.key, label=f.label, field_type=f.field_type, mode=f.mode,
                required=f.required, position=f.position, config=f.config or {},
                fixed_value=f.fixed_value,
                fixed_display=views.display_value(db, f.field_type, f.fixed_value),
                options_display=views.options_display(db, f),
            )
            for f in g.fields
        ],
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


@router.get("", response_model=list[FieldGroupOut])
def list_groups(
    search: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    """Every group; ``search`` matches the group's name, description or field names."""
    q = db.query(FieldGroup).options(selectinload(FieldGroup.fields))
    if search and search.strip():
        like = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace(
            "_", "\\_"
        ) + "%"
        q = q.filter(
            or_(
                FieldGroup.name.ilike(like, escape="\\"),
                FieldGroup.description.ilike(like, escape="\\"),
                FieldGroup.fields.any(FieldGroupField.label.ilike(like, escape="\\")),
            )
        )
    return [_out(db, g) for g in q.order_by(func.lower(FieldGroup.name)).all()]


@router.get("/{group_id}", response_model=FieldGroupOut)
def get_group(group_id: int, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return _out(db, _get(db, group_id))


@router.post("", response_model=FieldGroupOut, status_code=201)
def create_group(
    body: FieldGroupCreate, db: Session = Depends(get_db), user: User = Depends(require_manager)
):
    group = svc.create_group(db, body.model_dump(mode="json"), user)
    db.commit()
    return _out(db, group)


@router.patch("/{group_id}", response_model=FieldGroupOut)
def update_group(
    group_id: int,
    body: FieldGroupUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    group = svc.update_group(
        db, _get(db, group_id), body.model_dump(mode="json", exclude_unset=True), user
    )
    db.commit()
    db.refresh(group)
    return _out(db, group)


@router.delete("/{group_id}", status_code=204)
def delete_group(
    group_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager)
):
    svc.delete_group(db, _get(db, group_id), user)
    db.commit()
