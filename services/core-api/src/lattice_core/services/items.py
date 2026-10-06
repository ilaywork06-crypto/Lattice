"""Item lifecycle: create (from a template) / update / move / link / unlink /
state / delete.

These functions are the single source of truth for mutations. They are called
directly by managers and indirectly (after approval) by the change-request
executor, so the rules live in exactly one place.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from lattice_core.errors import DomainError
from lattice_core.models import (
    CardTracking,
    Document,
    FieldMode,
    FieldType,
    Item,
    ItemFieldValue,
    ItemState,
    ItemTemplate,
    ItemType,
    Location,
    StateHistory,
    TemplateField,
    User,
)
from lattice_core.services import fields as fields_svc
from lattice_core.services import files as files_svc
from lattice_core.services import serials as serials_svc
from lattice_core.services.audit import record_audit

__all__ = ["DomainError"]  # re-exported for callers that predate errors.py

# Hierarchy by item type: a card sits in an assembly or a setup, an assembly in
# a setup, a setup is always top of the tree. *Which* templates may sit inside
# which is narrower still — see ``template_children``.
_ALLOWED_PARENTS: dict[ItemType, set[ItemType]] = {
    ItemType.card: {ItemType.assembly, ItemType.setup},
    ItemType.assembly: {ItemType.setup},
    ItemType.setup: set(),
}

# Physical state has its own actions (move / link / state), each with its own
# rules and history, so an edit form never writes these directly.
_ACTION_ONLY = {
    FieldType.location: "move",
    FieldType.parent: "link/unlink",
    FieldType.status: "change state",
}


# ─────────────────────────── helpers ───────────────────────────
def _descendant_ids(item: Item) -> set[int]:
    """All ids beneath ``item`` (used for cascades and cycle checks)."""
    out: set[int] = set()
    stack = list(item.children)
    while stack:
        node = stack.pop()
        if node.id in out:
            continue
        out.add(node.id)
        stack.extend(node.children)
    return out


def _units(items, template_id: int) -> int:
    """Units of one template among ``items`` — destroyed ones take no place."""
    return sum(
        (c.quantity or 1)
        for c in items
        if c.template_id == template_id and c.state != ItemState.destroyed
    )


def _child_link(parent: Item, template_id: int):
    return next(
        (link for link in parent.template.child_links if link.child_template_id == template_id),
        None,
    )


def check_capacity(parent: Item, contents: list[Item]) -> None:
    """Refuse contents that exceed a template's maximum for any child template."""
    for link in parent.template.child_links:
        if link.max_count is None:
            continue
        units = _units(contents, link.child_template_id)
        if units > link.max_count:
            raise DomainError(
                f"'{parent.label}' can hold at most {link.max_count} × "
                f"'{link.child.name}' — this would make it {units}"
            )


def composition(item: Item) -> list[dict]:
    """Per allowed child template: what is inside against the template's limits."""
    rows = []
    for link in item.template.child_links:
        count = _units(item.children, link.child_template_id)
        rows.append({
            "template": link.child,
            "min_count": link.min_count,
            "max_count": link.max_count,
            "count": count,
            "missing": max(link.min_count - count, 0),
            "is_full": link.max_count is not None and count >= link.max_count,
        })
    return rows


def missing_children(item: Item) -> int:
    if item.type == ItemType.card:
        return 0
    return sum(
        max(link.min_count - _units(item.children, link.child_template_id), 0)
        for link in item.template.child_links
        if link.min_count
    )


def validate_link(child: Item, parent: Item, *, capacity: bool = True) -> None:
    if child.id is not None and child.id == parent.id:
        raise DomainError("An item cannot be linked to itself")
    allowed = _ALLOWED_PARENTS[child.type]
    if parent.type not in allowed:
        raise DomainError(f"A {child.type.value} cannot be linked to a {parent.type.value}")
    if child.template not in parent.template.child_templates:
        raise DomainError(
            f"'{parent.template.name}' templates don't include '{child.template.name}' — "
            f"add it to that template's contents to allow it"
        )
    if child.id is not None and parent.id in _descendant_ids(child):
        raise DomainError("That would create a cycle in the hierarchy")
    if capacity:
        others = [c for c in parent.children if c is not child and c.id != child.id]
        check_capacity(parent, [*others, child])


def default_desiccator(db: Session) -> Location | None:
    return (
        db.query(Location)
        .filter(Location.is_desiccator.is_(True))
        .order_by(Location.name)
        .first()
    )


def write_system_value(db: Session, item: Item, field_type: FieldType, value) -> None:
    """Store a system field's value in the item's own column/association."""
    if field_type == FieldType.industry:
        item.industry_id = value
    elif field_type == FieldType.project:
        item.project_id = value
    elif field_type == FieldType.team:
        item.team_id = value
    elif field_type == FieldType.responsible:
        item.responsible_id = value
    elif field_type == FieldType.managers:
        ids = value or []
        item.managers = db.query(User).filter(User.id.in_(ids)).all() if ids else []
    elif field_type == FieldType.status:
        item.state = ItemState(value) if value else ItemState.built
    elif field_type == FieldType.quantity:
        item.quantity = value or 1
    elif field_type == FieldType.location:
        item.location_id = value
    # parent is applied through link_item


def read_system_value(item: Item, field_type: FieldType):
    return {
        FieldType.industry: lambda: item.industry_id,
        FieldType.project: lambda: item.project_id,
        FieldType.team: lambda: item.team_id,
        FieldType.responsible: lambda: item.responsible_id,
        FieldType.managers: lambda: sorted(m.id for m in item.managers),
        FieldType.status: lambda: item.state.value,
        FieldType.quantity: lambda: item.quantity,
        FieldType.location: lambda: item.location_id,
        FieldType.parent: lambda: item.parent_id,
    }[field_type]()


def _resolve_values(
    db: Session,
    template: ItemTemplate,
    supplied: dict,
    *,
    creating: bool,
    item: Item | None = None,
) -> dict[int, object]:
    """Validate supplied values against the template → ``{field_id: value}``.

    Every problem is collected (not just the first), so a form or a spreadsheet
    row can show them all at once.
    """
    by_key = {f.key: f for f in template.fields}
    errors: list[dict] = []
    unknown = [k for k in supplied if k not in by_key]
    for k in unknown:
        errors.append({"field": k, "error": f"'{k}' is not a field of '{template.name}'"})

    out: dict[int, object] = {}
    for f in template.fields:
        present = f.key in supplied
        if f.mode == FieldMode.fixed:
            if present and creating:
                errors.append({
                    "field": f.key, "label": f.label,
                    "error": "is set on the template and cannot be changed per item",
                })
            elif present:
                errors.append({
                    "field": f.key, "label": f.label,
                    "error": "is set on the template — edit the template to change it",
                })
            continue
        if not creating and not present:
            continue
        if not creating and f.field_type in _ACTION_ONLY:
            errors.append({
                "field": f.key, "label": f.label,
                "error": f"use the '{_ACTION_ONLY[f.field_type]}' action to change it",
            })
            continue
        raw = supplied.get(f.key) if present else None
        try:
            value = fields_svc.coerce_value(db, f.field_type, raw, f.config)
            if fields_svc.is_empty(value) and creating:
                value = fields_svc.default_value(f)
            if not fields_svc.is_empty(value):
                fields_svc.check_choice(f, value)
        except ValueError as exc:
            errors.append({"field": f.key, "label": f.label, "error": str(exc)})
            continue
        if f.required and fields_svc.is_empty(value):
            errors.append({"field": f.key, "label": f.label, "error": "is required"})
            continue
        out[f.id] = value

    if errors:
        raise DomainError(
            "; ".join(f"{e.get('label') or e['field']}: {e['error']}" for e in errors),
            errors,
        )
    return out


def _attach_files(db: Session, item: Item, field: TemplateField, doc_ids: list[int]) -> None:
    current = {
        d.id: d
        for d in db.query(Document).filter(
            Document.item_id == item.id, Document.field_id == field.id
        )
    }
    for doc_id in doc_ids or []:
        if doc_id in current:
            continue
        doc = db.get(Document, doc_id)
        if doc is None:
            raise DomainError(f"Uploaded file #{doc_id} no longer exists")
        if doc.item_id is not None or doc.template_id is not None:
            raise DomainError(f"File '{doc.name}' already belongs to another record")
        doc.item_id = item.id
        doc.field_id = field.id
    for doc_id, doc in current.items():
        if doc_id not in (doc_ids or []):
            files_svc.delete_document(db, doc)


def _write_value(db: Session, item: Item, field: TemplateField, value) -> None:
    if field.field_type in fields_svc.SYSTEM_FIELD_TYPES:
        write_system_value(db, item, field.field_type, value)
        return
    if field.field_type == FieldType.files:
        _attach_files(db, item, field, value or [])
        return
    row = next((v for v in item.field_values if v.field_id == field.id), None)
    if fields_svc.is_empty(value):
        if row is not None:
            item.field_values.remove(row)
        return
    if row is None:
        item.field_values.append(ItemFieldValue(field_id=field.id, value=value))
    else:
        row.value = value


def effective_value(db: Session, item: Item, field: TemplateField):
    """What this item shows for a field: the template's, its own, or a column."""
    if field.field_type == FieldType.files:
        q = db.query(Document).filter(Document.field_id == field.id)
        q = (
            q.filter(Document.template_id == field.template_id)
            if field.mode == FieldMode.fixed
            else q.filter(Document.item_id == item.id)
        )
        return [d.id for d in q.order_by(Document.created_at)]
    if field.field_type in fields_svc.SYSTEM_FIELD_TYPES:
        return read_system_value(item, field.field_type)
    if field.mode == FieldMode.fixed:
        return field.fixed_value
    row = next((v for v in item.field_values if v.field_id == field.id), None)
    return row.value if row else None


def _enforce_quantity(item: Item) -> None:
    if item.type != ItemType.card or item.template.tracking is not CardTracking.quantity:
        if (item.quantity or 1) != 1:
            raise DomainError(
                "Only commercial cards hold a quantity; every other item is one unit"
            )
        item.quantity = 1


# ─────────────────────────── create ───────────────────────────
def create_item(db: Session, data: dict, user: User) -> Item:
    """Create one item from its template.

    ``data``: ``template_id``, ``values`` (``{field key: value}``), optional
    ``serial`` (otherwise the next one is issued) and ``child_ids`` (existing
    items to place inside the new one).
    """
    template = db.get(ItemTemplate, data.get("template_id")) if data.get("template_id") else None
    if template is None:
        raise DomainError("Items are created from a template — choose an existing template")

    values = _resolve_values(db, template, dict(data.get("values") or {}), creating=True)

    item = Item(
        template=template,
        type=template.type,
        state=ItemState.built,
        quantity=1,
        created_by=user.id,
    )
    parent_id = None
    for f in template.fields:
        value = f.fixed_value if f.mode == FieldMode.fixed else values.get(f.id)
        if f.field_type == FieldType.parent:
            parent_id = value
        elif f.field_type in fields_svc.SYSTEM_FIELD_TYPES:
            write_system_value(db, item, f.field_type, value)
    _enforce_quantity(item)

    serial = data.get("serial")
    item.serial = (
        serials_svc.validate_manual(db, template, serial)
        if serial and str(serial).strip()
        else serials_svc.next_serial(db, template)
    )

    parent = None
    if parent_id:
        parent = db.get(Item, parent_id)
        if parent is None:
            raise DomainError(f"Parent item #{parent_id} not found")
        validate_link(item, parent)
    if item.location_id is None and parent is None and item.type == ItemType.card:
        # A new card goes to the desiccator unless told otherwise.
        desiccator = default_desiccator(db)
        item.location_id = desiccator.id if desiccator else None

    db.add(item)
    db.flush()

    for f in template.fields:
        if f.mode != FieldMode.fixed and f.field_type not in fields_svc.SYSTEM_FIELD_TYPES:
            _write_value(db, item, f, values.get(f.id))

    db.add(StateHistory(item_id=item.id, state=item.state, note="Item created",
                        changed_by=user.id))
    record_audit(
        db,
        item=item,
        action="create",
        summary=f"Created {item.type.value} '{item.label}'",
        user=user,
        details={"template_id": template.id, "serial": item.serial},
    )

    if parent is not None:
        link_item(db, item, parent, user)
    for cid in list(dict.fromkeys(data.get("child_ids") or [])):
        child = db.get(Item, cid)
        if child is None:
            raise DomainError(f"Item #{cid} not found")
        link_item(db, child, item, user)
    return item


# ─────────────────────────── update ───────────────────────────
def update_item(db: Session, item: Item, data: dict, user: User) -> Item:
    """Edit an item's own values (and optionally its serial).

    ``data``: ``values`` (only the fields being changed) and/or ``serial``.
    Template (white) fields are edited on the template; location, parent and
    state go through their own actions.
    """
    template = item.template
    supplied = dict(data.get("values") or {})
    values = _resolve_values(db, template, supplied, creating=False, item=item)
    by_id = {f.id: f for f in template.fields}
    changed: dict[str, list] = {}

    for field_id, value in values.items():
        f = by_id[field_id]
        before = effective_value(db, item, f)
        if f.field_type == FieldType.managers:
            value = sorted(value or [])
        if before == value or (fields_svc.is_empty(before) and fields_svc.is_empty(value)):
            continue
        _write_value(db, item, f, value)
        changed[f.label] = [before, value]
    _enforce_quantity(item)
    if item.parent is not None and item.state != ItemState.destroyed:
        check_capacity(item.parent, list(item.parent.children))

    serial = data.get("serial")
    if serial is not None and str(serial).strip().upper() != item.serial:
        new = serials_svc.validate_manual(db, template, serial, item)
        changed["serial"] = [item.serial, new]
        item.serial = new

    if changed:
        record_audit(
            db,
            item=item,
            action="update",
            summary=f"Updated {item.type.value} '{item.label}' ({', '.join(changed)})",
            user=user,
            details={"changed": changed},
        )
    return item


# ─────────────────────────── move (cascade) ───────────────────────────
def move_item(
    db: Session, item: Item, location_id: int, user: User, note: str | None = None
) -> Item:
    """Move an item to a new location.

    Cascades *downward* to every descendant — moving a container drags all of
    its contents (§3). A **linked item cannot be moved on its own**: being
    linked means it physically sits inside its parent, so it is wherever the
    parent is. The only honest way to relocate it is to move the parent, or to
    unlink it first — and the error says which (§3).
    """
    if db.get(Location, location_id) is None:
        raise DomainError(f"Location #{location_id} not found")
    if item.parent_id is not None:
        parent = db.get(Item, item.parent_id)
        where = (
            f"{parent.type.value} '{parent.label}'" if parent is not None
            else f"item #{item.parent_id}"
        )
        raise DomainError(
            f"'{item.label}' sits inside {where}, so it has no location of its "
            f"own. Move {where} instead — everything inside it follows — or "
            f"unlink '{item.label}' first if it has physically come out."
        )

    old_location = item.location_id
    item.location_id = location_id

    moved_children: list[int] = []
    stack = list(item.children)
    while stack:
        child = stack.pop()
        child.location_id = location_id
        moved_children.append(child.id)
        stack.extend(child.children)

    new_loc = db.get(Location, location_id)
    record_audit(
        db,
        item=item,
        action="move",
        summary=(
            f"Moved {item.type.value} '{item.label}' to '{new_loc.name}'"
            + (f" (+{len(moved_children)} linked items)" if moved_children else "")
        ),
        user=user,
        details={
            "from_location_id": old_location,
            "to_location_id": location_id,
            "cascaded_item_ids": moved_children,
            "note": note,
        },
    )
    return item


# ─────────────────────────── link / unlink ───────────────────────────
def link_item(
    db: Session, child: Item, parent: Item, user: User, *, capacity: bool = True
) -> Item:
    validate_link(child, parent, capacity=capacity)
    child.parent_id = parent.id
    child.parent = parent
    # Assembled items inherit the container's location — and so does everything
    # already inside the child (a container drags its whole contents).
    cascaded: list[int] = []
    if parent.location_id is not None:
        child.location_id = parent.location_id
        for cid in _descendant_ids(child):
            desc = db.get(Item, cid)
            if desc is not None:
                desc.location_id = parent.location_id
                cascaded.append(cid)
    record_audit(
        db,
        item=child,
        action="link",
        summary=f"Linked {child.type.value} '{child.label}' into '{parent.label}'"
        + (f" (+{len(cascaded)} nested items relocated)" if cascaded else ""),
        user=user,
        details={"parent_id": parent.id, "parent_name": parent.label, "cascaded": cascaded},
    )
    return child


def set_children(db: Session, parent: Item, child_ids: list[int], user: User) -> Item:
    """Make the parent's contents exactly ``child_ids``.

    Everything is validated before anything is written, so a bad id can't leave
    the tree half-edited, and the add/remove both go through link/unlink — the
    cascade and the audit trail behave exactly as they do anywhere else.
    """
    desired = list(dict.fromkeys(child_ids))
    current = {c.id for c in parent.children}

    to_add: list[Item] = []
    for cid in desired:
        if cid in current:
            continue
        child = db.get(Item, cid)
        if child is None:
            raise DomainError(f"Item #{cid} not found")
        validate_link(child, parent, capacity=False)
        to_add.append(child)
    to_remove = [c for c in list(parent.children) if c.id not in set(desired)]
    check_capacity(parent, [c for c in parent.children if c.id in set(desired)] + to_add)

    for child in to_remove:
        unlink_item(db, child, user)
    for child in to_add:
        link_item(db, child, parent, user, capacity=False)

    if to_add or to_remove:
        record_audit(
            db,
            item=parent,
            action="update",
            summary=(
                f"Updated contents of {parent.type.value} '{parent.label}' "
                f"(+{len(to_add)} / -{len(to_remove)})"
            ),
            user=user,
            details={"added": [c.id for c in to_add], "removed": [c.id for c in to_remove]},
        )
    return parent


def unlink_item(db: Session, child: Item, user: User, location_id: int | None = None) -> Item:
    """Take an item out of its container.

    It keeps the container's location (that is where it physically is) unless a
    new one is given; a loose card returns to stock only if that location is
    part of the desiccator.
    """
    old_parent = child.parent_id
    if old_parent is None:
        raise DomainError(f"'{child.label}' is not inside anything")
    if child.parent is not None and child in child.parent.children:
        child.parent.children.remove(child)
    child.parent_id = None
    if location_id is not None:
        if db.get(Location, location_id) is None:
            raise DomainError(f"Location #{location_id} not found")
        child.location_id = location_id
    record_audit(
        db,
        item=child,
        action="unlink",
        summary=f"Unlinked {child.type.value} '{child.label}'",
        user=user,
        details={"previous_parent_id": old_parent, "location_id": child.location_id},
    )
    return child


# ─────────────────────────── state machine ───────────────────────────
def change_state(
    db: Session, item: Item, new_state: ItemState, note: str | None, user: User
) -> Item:
    old_state = item.state
    if old_state == new_state:
        return item

    # Transitions into or out of "faulty" demand an explanation.
    requires_note = new_state == ItemState.faulty or old_state == ItemState.faulty
    if requires_note and not (note and note.strip()):
        raise DomainError(
            "A note explaining how the fault occurred or was resolved is required "
            "for transitions into or out of 'faulty'."
        )

    item.state = new_state
    if old_state == ItemState.destroyed and item.parent is not None:
        # A destroyed unit took no place in its container; back in service it does.
        check_capacity(item.parent, list(item.parent.children))
    db.add(StateHistory(item_id=item.id, state=new_state, note=note, changed_by=user.id))
    record_audit(
        db,
        item=item,
        action="state_change",
        summary=f"State of '{item.label}': {old_state.value} → {new_state.value}",
        user=user,
        details={"from": old_state.value, "to": new_state.value, "note": note},
    )
    return item


# ─────────────────────────── delete ───────────────────────────
def delete_item(db: Session, item: Item, user: User) -> None:
    record_audit(
        db,
        item=item,
        action="delete",
        summary=f"Deleted {item.type.value} '{item.label}'",
        user=user,
        details={"type": item.type.value, "serial": item.serial},
    )
    for doc in list(item.documents):
        files_svc.delete_document(db, doc)
    for child in list(item.children):
        child.parent_id = None
    db.flush()
    db.delete(item)
