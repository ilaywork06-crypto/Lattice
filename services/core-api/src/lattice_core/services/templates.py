"""Templates: the blueprints every item is created from.

Managers edit templates directly; editors propose edits through change requests
(which call these same functions on approval).

**A template edit reaches every item made from it.** A *fixed* (white) field's
value is read through the template, so changing it changes all items at once;
for system fields (catalog values, responsible, managers) the value also lives
in real columns on the items, and those are rewritten here in the same
transaction — e.g. fixing a new manager on a template moves every one of its
items under that manager.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from lattice_core.errors import DomainError
from lattice_core.models import (
    CardType,
    Document,
    FieldMode,
    FieldType,
    Item,
    ItemFieldValue,
    ItemTemplate,
    ItemType,
    StockThreshold,
    TemplateField,
    User,
    card_tracking,
)
from lattice_core.services import fields as fields_svc
from lattice_core.services import files as files_svc
from lattice_core.services import serials as serials_svc
from lattice_core.services.audit import record_audit

# Which kinds of template may be placed inside which.
ALLOWED_CHILD_TYPES: dict[ItemType, frozenset[ItemType]] = {
    ItemType.setup: frozenset({ItemType.assembly, ItemType.card}),
    ItemType.assembly: frozenset({ItemType.card}),
    ItemType.card: frozenset(),
}

# System fields whose (fixed) value is pushed into the items' own columns.
_PROPAGATED = frozenset({
    FieldType.industry, FieldType.project, FieldType.team, FieldType.responsible,
    FieldType.managers,
})


# ─────────────────────────── helpers ───────────────────────────
def _check_name(db: Session, item_type: ItemType, name: str, exclude_id: int | None) -> str:
    clean = (name or "").strip()
    if not clean:
        raise DomainError("A template needs a name")
    clash = (
        db.query(ItemTemplate)
        .filter(
            ItemTemplate.type == item_type,
            func.lower(ItemTemplate.name) == clean.lower(),
            ItemTemplate.id != (exclude_id or -1),
        )
        .first()
    )
    if clash:
        raise DomainError(
            f"A {item_type.value} template named '{clash.name}' already exists — each "
            "named card, assembly or setup has exactly one template"
        )
    return clean


def _check_prefix(db: Session, item_type: ItemType, prefix: str, exclude_id: int | None) -> str:
    value = serials_svc.normalize_prefix(prefix)
    clash = (
        db.query(ItemTemplate)
        .filter(
            ItemTemplate.type == item_type,
            ItemTemplate.serial_prefix == value,
            ItemTemplate.id != (exclude_id or -1),
        )
        .first()
    )
    if clash:
        raise DomainError(
            f"The serial prefix '{value}' is already used by the {item_type.value} "
            f"template '{clash.name}'"
        )
    return value


def _check_card_type(item_type: ItemType, card_type) -> CardType | None:
    if item_type == ItemType.card:
        if card_type is None:
            raise DomainError(
                "A card template needs a card type (copied / house / white / factory / "
                "commercial)"
            )
        return CardType(card_type)
    if card_type is not None:
        raise DomainError("Only card templates have a card type")
    return None


def _resolve_children(db: Session, tpl_type: ItemType, ids: list[int], self_id: int | None):
    wanted = list(dict.fromkeys(ids))
    children = db.query(ItemTemplate).filter(ItemTemplate.id.in_(wanted)).all() if wanted else []
    if len(children) != len(wanted):
        raise DomainError("One or more of the chosen templates no longer exist")
    allowed = ALLOWED_CHILD_TYPES[tpl_type]
    for c in children:
        if c.id == self_id:
            raise DomainError("A template cannot contain itself")
        if c.type not in allowed:
            raise DomainError(
                f"A {tpl_type.value} template cannot contain {c.type.value} templates "
                f"('{c.name}')"
            )
    order = {tid: i for i, tid in enumerate(wanted)}
    return sorted(children, key=lambda c: order[c.id])


def _spec_from_field(f: TemplateField) -> dict:
    return {
        "id": f.id, "key": f.key, "label": f.label, "field_type": f.field_type,
        "mode": f.mode, "required": f.required, "config": f.config,
        "fixed_value": f.fixed_value,
    }


def _items_of(db: Session, tpl: ItemTemplate):
    return db.query(Item).filter(Item.template_id == tpl.id)


def _propagate(db: Session, tpl: ItemTemplate, field_type: FieldType, value) -> int:
    """Write a template-level system value into every item's own column."""
    from lattice_core.services.items import write_system_value

    items = _items_of(db, tpl).all()
    for item in items:
        write_system_value(db, item, field_type, value)
    return len(items)


def _clear_system(db: Session, tpl: ItemTemplate, field_type: FieldType) -> None:
    """A removed system field stops describing the items; clear what it set."""
    if field_type in _PROPAGATED:
        _propagate(db, tpl, field_type, [] if field_type == FieldType.managers else None)


# ─────────────────────────── create ───────────────────────────
def create_template(db: Session, data: dict, user: User) -> ItemTemplate:
    try:
        item_type = ItemType(data["type"])
    except (KeyError, ValueError):
        raise DomainError("A template needs a type: setup, assembly or card") from None
    card_type = _check_card_type(item_type, data.get("card_type"))
    tpl = ItemTemplate(
        type=item_type,
        name=_check_name(db, item_type, data.get("name"), None),
        card_type=card_type,
        serial_prefix=_check_prefix(db, item_type, data.get("serial_prefix"), None),
        description=(data.get("description") or "").strip() or None,
        created_by=user.id,
    )
    specs = fields_svc.normalize_field_specs(db, item_type, card_type, data.get("fields") or [])
    for spec in specs:
        if spec["id"] is not None:
            raise DomainError("A new template's fields cannot refer to existing field ids")
        spec.pop("id")
        tpl.fields.append(TemplateField(**spec))
    tpl.child_templates = _resolve_children(
        db, item_type, data.get("child_template_ids") or [], None
    )
    db.add(tpl)
    db.flush()
    record_audit(
        db,
        template=tpl,
        action="template.create",
        summary=f"Created {item_type.value} template '{tpl.name}' ({tpl.serial_prefix})",
        user=user,
        details={"fields": [s["label"] for s in specs]},
    )
    return tpl


# ─────────────────────────── update ───────────────────────────
def update_template(db: Session, tpl: ItemTemplate, data: dict, user: User) -> ItemTemplate:  # noqa: C901
    changes: dict[str, object] = {}
    item_count = _items_of(db, tpl).count()

    if "name" in data and data["name"] is not None:
        name = _check_name(db, tpl.type, data["name"], tpl.id)
        if name != tpl.name:
            changes["name"] = [tpl.name, name]
            tpl.name = name
    if "serial_prefix" in data and data["serial_prefix"] is not None:
        prefix = _check_prefix(db, tpl.type, data["serial_prefix"], tpl.id)
        if prefix != tpl.serial_prefix:
            # Existing items keep the serial they were issued — a serial is the
            # label on the physical board — new items use the new prefix.
            changes["serial_prefix"] = [tpl.serial_prefix, prefix]
            tpl.serial_prefix = prefix
    if "description" in data:
        desc = (data.get("description") or "").strip() or None
        if desc != tpl.description:
            changes["description"] = True
            tpl.description = desc
    if "card_type" in data and data["card_type"] is not None:
        new_ct = _check_card_type(tpl.type, data["card_type"])
        if new_ct != tpl.card_type:
            if card_tracking(new_ct) != card_tracking(tpl.card_type):
                many = _items_of(db, tpl).filter(Item.quantity > 1).count()
                if many:
                    raise DomainError(
                        f"{many} item(s) of '{tpl.name}' hold more than one unit; a "
                        f"{new_ct.value} card is tracked one unit per serial"
                    )
            changes["card_type"] = [tpl.card_type.value, new_ct.value]
            tpl.card_type = new_ct

    # Fields: the submitted list is the template's full field list after the edit.
    existing = {f.id: f for f in tpl.fields}
    raw_specs = data.get("fields")
    specs = fields_svc.normalize_field_specs(
        db,
        tpl.type,
        tpl.card_type,
        raw_specs if raw_specs is not None else [_spec_from_field(f) for f in tpl.fields],
        existing,
    )
    kept_ids = {s["id"] for s in specs if s["id"] is not None}
    affected = 0

    for fid, f in existing.items():
        if fid in kept_ids:
            continue
        _clear_system(db, tpl, f.field_type)
        for doc in db.query(Document).filter(Document.field_id == f.id).all():
            files_svc.delete_document(db, doc)
        changes.setdefault("removed_fields", []).append(f.label)
        tpl.fields.remove(f)
    db.flush()

    for spec in specs:
        fid = spec.pop("id")
        if fid is None:
            f = TemplateField(**spec)
            tpl.fields.append(f)
            db.flush()
            changes.setdefault("added_fields", []).append(f.label)
            if f.mode == FieldMode.fixed and f.field_type in _PROPAGATED:
                affected = max(affected, _propagate(db, tpl, f.field_type, f.fixed_value))
            continue

        f = existing[fid]
        before_mode, before_value = f.mode, f.fixed_value
        if f.field_type == FieldType.files and before_mode != spec["mode"]:
            has_docs = db.query(Document).filter(Document.field_id == f.id).count()
            if has_docs and FieldMode.fixed in (before_mode, spec["mode"]):
                raise DomainError(
                    f"'{f.label}' already has files; remove them before switching it "
                    "between a template value and a per-item value"
                )
        diff = [
            k for k in ("key", "label", "mode", "required", "position", "config", "fixed_value")
            if getattr(f, k) != spec[k]
        ]
        for k in diff:
            setattr(f, k, spec[k])
        if set(diff) - {"position"}:
            changes.setdefault("changed_fields", []).append(f.label)

        now_fixed = f.mode == FieldMode.fixed
        was_fixed = before_mode == FieldMode.fixed
        if now_fixed and (not was_fixed or before_value != f.fixed_value):
            if f.field_type in _PROPAGATED:
                affected = max(affected, _propagate(db, tpl, f.field_type, f.fixed_value))
            elif f.field_type != FieldType.files:
                # The template value now speaks for every item.
                db.query(ItemFieldValue).filter(ItemFieldValue.field_id == f.id).delete(
                    synchronize_session=False
                )
                affected = max(affected, item_count)
        elif was_fixed and not now_fixed and f.field_type not in _PROPAGATED:
            # Keep what every item showed until now as its own value.
            if f.field_type != FieldType.files and before_value is not None:
                for item in _items_of(db, tpl).all():
                    db.add(ItemFieldValue(item_id=item.id, field_id=f.id, value=before_value))

    tpl.fields.sort(key=lambda f: f.position)

    if "child_template_ids" in data and data["child_template_ids"] is not None:
        children = _resolve_children(db, tpl.type, data["child_template_ids"], tpl.id)
        before = {c.id for c in tpl.child_templates}
        after = {c.id for c in children}
        for removed_id in before - after:
            in_use = _linked_children_count(db, tpl.id, removed_id)
            if in_use:
                child = db.get(ItemTemplate, removed_id)
                raise DomainError(
                    f"{in_use} item(s) of '{child.name}' currently sit inside items of "
                    f"'{tpl.name}' — unlink them before removing that template from the list"
                )
        if before != after:
            changes["child_templates"] = sorted(after)
        tpl.child_templates = children

    db.flush()
    if changes:
        record_audit(
            db,
            template=tpl,
            action="template.update",
            summary=(
                f"Updated template '{tpl.name}' ({', '.join(changes)})"
                + (f" — applied to {affected} item(s)" if affected else "")
            ),
            user=user,
            details={"changes": changes, "items_affected": affected},
        )
    return tpl


def _linked_children_count(db: Session, parent_tpl_id: int, child_tpl_id: int) -> int:
    parent = aliased(Item)
    return (
        db.query(func.count(Item.id))
        .join(parent, Item.parent_id == parent.id)
        .filter(Item.template_id == child_tpl_id, parent.template_id == parent_tpl_id)
        .scalar()
        or 0
    )


# ─────────────────────────── delete ───────────────────────────
def delete_template(db: Session, tpl: ItemTemplate, user: User) -> None:
    count = _items_of(db, tpl).count()
    if count:
        raise DomainError(
            f"'{tpl.name}' still has {count} item(s); a template can only be deleted "
            "once nothing was made from it"
        )
    for doc in db.query(Document).filter(Document.template_id == tpl.id).all():
        files_svc.delete_document(db, doc)
    db.query(StockThreshold).filter(StockThreshold.template_id == tpl.id).delete(
        synchronize_session=False
    )
    record_audit(
        db,
        template=None,
        action="template.delete",
        summary=f"Deleted {tpl.type.value} template '{tpl.name}'",
        user=user,
        details={"template_id": tpl.id, "name": tpl.name},
    )
    db.delete(tpl)


# ─────────────────────────── reads ───────────────────────────
def allowed_parent_templates(db: Session, tpl: ItemTemplate) -> list[ItemTemplate]:
    return list(tpl.parent_templates)
