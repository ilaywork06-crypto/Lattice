"""Field groups: named, reusable sets of field definitions kept in the catalog.

A group is a preset for the template editor — "load the group" copies its
fields into the template being written. Templates never stay linked to a group,
so editing or deleting a group cannot change a template (or its items) behind
anyone's back.

Fields are validated exactly as template fields are, against the most
permissive template kind (a commercial card), so anything a group holds is
something some template can use; whether it fits a *particular* template is
checked when that template is saved.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from lattice_core.errors import DomainError
from lattice_core.models import (
    CardType,
    FieldGroup,
    FieldGroupField,
    FieldMode,
    FieldType,
    ItemType,
    User,
)
from lattice_core.services import fields as fields_svc
from lattice_core.services.audit import record_audit


def _check_name(db: Session, name: str | None, exclude_id: int | None) -> str:
    clean = (name or "").strip()
    if not clean:
        raise DomainError("A field group needs a name")
    clash = (
        db.query(FieldGroup)
        .filter(func.lower(FieldGroup.name) == clean.lower(), FieldGroup.id != (exclude_id or -1))
        .first()
    )
    if clash:
        raise DomainError(f"A field group named '{clash.name}' already exists")
    return clean


def _specs(db: Session, raw: list[dict]) -> list[dict]:
    if not raw:
        raise DomainError("A field group needs at least one field")
    specs = fields_svc.normalize_field_specs(
        db, ItemType.card, CardType.commercial, [{**f, "id": None} for f in raw]
    )
    for s in specs:
        s.pop("id")
    return specs


def create_group(db: Session, data: dict, user: User) -> FieldGroup:
    group = FieldGroup(
        name=_check_name(db, data.get("name"), None),
        description=(data.get("description") or "").strip() or None,
        created_by=user.id,
    )
    group.fields = [FieldGroupField(**s) for s in _specs(db, data.get("fields") or [])]
    db.add(group)
    db.flush()
    record_audit(
        db,
        action="field_group.create",
        summary=f"Created the field group '{group.name}' ({len(group.fields)} fields)",
        user=user,
        details={"field_group_id": group.id, "fields": [f.label for f in group.fields]},
    )
    return group


def update_group(db: Session, group: FieldGroup, data: dict, user: User) -> FieldGroup:
    if data.get("name") is not None:
        group.name = _check_name(db, data["name"], group.id)
    if "description" in data:
        group.description = (data.get("description") or "").strip() or None
    if data.get("fields") is not None:
        specs = _specs(db, data["fields"])
        group.fields.clear()
        db.flush()  # free the (group, key) pairs before re-adding
        group.fields.extend(FieldGroupField(**s) for s in specs)
    db.flush()
    record_audit(
        db,
        action="field_group.update",
        summary=f"Updated the field group '{group.name}'",
        user=user,
        details={"field_group_id": group.id, "fields": [f.label for f in group.fields]},
    )
    return group


def delete_group(db: Session, group: FieldGroup, user: User) -> None:
    record_audit(
        db,
        action="field_group.delete",
        summary=f"Deleted the field group '{group.name}'",
        user=user,
        details={"field_group_id": group.id},
    )
    db.delete(group)


def forget_reference(db: Session, field_types: set[FieldType], ref_id: int) -> None:
    """Drop a deleted row (user, location, catalog value) from every group's
    list options and fixed values — JSON can't carry a foreign key."""
    rows = db.query(FieldGroupField).filter(FieldGroupField.field_type.in_(list(field_types)))
    for f in rows:
        options = (f.config or {}).get("options")
        if options and ref_id in options:
            f.config = {**f.config, "options": [o for o in options if o != ref_id]}
        if f.mode == FieldMode.fixed:
            if f.fixed_value == ref_id:
                f.fixed_value = None
            elif isinstance(f.fixed_value, list) and ref_id in f.fixed_value:
                f.fixed_value = [v for v in f.fixed_value if v != ref_id]
