"""Item lifecycle: create / update / move / link / unlink / state / delete.

These functions are the single source of truth for mutations. They are called
directly by managers and indirectly (after approval) by the change-request
executor, so the rules live in exactly one place.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from lattice_core.models import (
    CardType,
    Item,
    ItemState,
    ItemType,
    StateHistory,
    StorageStatus,
    User,
)
from lattice_core.services import catalog as catalog_svc
from lattice_core.services.audit import record_audit


class DomainError(ValueError):
    """Raised on an invalid domain operation (mapped to HTTP 400)."""


# ─────────────────────── relationship rules ───────────────────────
_ALLOWED_PARENTS: dict[ItemType, set[ItemType]] = {
    # A setup can contain assemblies *and* cards directly (§8); an assembly can
    # contain cards; a setup is always top-of-tree.
    ItemType.card: {ItemType.assembly, ItemType.setup},
    ItemType.assembly: {ItemType.setup},
    ItemType.setup: set(),
}


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


def validate_link(child: Item, parent: Item) -> None:
    if child.id == parent.id:
        raise DomainError("An item cannot be linked to itself")
    if child.is_template or parent.is_template:
        raise DomainError("Templates cannot take part in the hierarchy")
    allowed = _ALLOWED_PARENTS[child.type]
    if parent.type not in allowed:
        raise DomainError(
            f"A {child.type.value} cannot be linked to a {parent.type.value}"
        )
    # Defensive cycle guard: the strict type rules already forbid cycles, but
    # never let a parent be one of the child's own descendants.
    if parent.id in _descendant_ids(child):
        raise DomainError("That would create a cycle in the hierarchy")


def _check_unique_serial(db: Session, item: Item) -> None:
    """A unique card's serial must be globally unique (data reliability, §2/§12)."""
    if item.type != ItemType.card or item.card_type != CardType.unique:
        return
    if not item.serial:
        return
    clash = (
        db.query(func.count(Item.id))
        .filter(
            Item.serial == item.serial,
            Item.id != (item.id or -1),
            Item.is_template.is_(False),
        )
        .scalar()
    )
    if clash:
        raise DomainError(f"Serial '{item.serial}' is already used by another unique card")


def _default_storage(item: Item) -> StorageStatus | None:
    if item.type != ItemType.card:
        return None
    return StorageStatus.assembled if item.parent_id else StorageStatus.desiccator


# ─────────────────────────── create ───────────────────────────
def create_item(db: Session, data: dict, user: User) -> Item:
    manager_ids = data.pop("manager_ids", []) or []
    child_ids = data.pop("child_ids", []) or []
    parent_id = data.get("parent_id")
    is_template = bool(data.get("is_template"))

    # Templates are standalone blueprints — no hierarchy involvement.
    if is_template:
        data["parent_id"] = parent_id = None
        child_ids = []

    try:
        catalog_svc.validate_item_catalog(db, data.get("project"), data.get("industry"))
    except catalog_svc.CatalogError as exc:
        raise DomainError(str(exc)) from exc

    item = Item(**{k: v for k, v in data.items() if hasattr(Item, k)})
    _check_unique_serial(db, item)

    if parent_id:
        parent = db.get(Item, parent_id)
        if parent is None:
            raise DomainError(f"Parent item {parent_id} not found")
        validate_link(item, parent)
        if item.location_id is None:
            item.location_id = parent.location_id

    if item.type == ItemType.card and item.storage_status is None and not is_template:
        item.storage_status = _default_storage(item)

    if manager_ids:
        item.managers = db.query(User).filter(User.id.in_(manager_ids)).all()

    db.add(item)
    db.flush()

    db.add(
        StateHistory(
            item_id=item.id, state=item.state, note="Item created", changed_by=user.id
        )
    )
    record_audit(
        db,
        item=item,
        action="create",
        summary=f"Created {item.type.value} '{item.name}'"
        + (" (template)" if is_template else ""),
        user=user,
        details={"type": item.type.value, "is_template": is_template},
    )

    # Bidirectional linking (§6/§8): adopt the requested existing items as
    # children, dragging their location to match (§9).
    for cid in child_ids:
        if cid == item.id:
            continue
        child = db.get(Item, cid)
        if child is None:
            raise DomainError(f"Item {cid} not found")
        link_item(db, child, item, user)

    return item


# ─────────────────────────── update ───────────────────────────
_MUTABLE_FIELDS = {
    "name", "industry", "project", "team", "description", "dmz",
    "card_type", "responsible", "lead", "production_date", "version",
    "serial", "storage_status",
}


def update_item(db: Session, item: Item, data: dict, user: User) -> Item:
    manager_ids = data.pop("manager_ids", None)
    # Deliberately *not* a member of _MUTABLE_FIELDS: a location change is a
    # move, and §3 requires it to cascade to every descendant. Writing the
    # column here would strand an assembly's cards at the old location, so it
    # is handed to move_item below — the one place that owns the cascade rule.
    new_location_id = data.pop("location_id", None)
    # Same story for state: it owns state history and the faulty-note rule, so
    # it goes through change_state rather than being written as a plain column.
    new_state = data.pop("state", None)
    state_note = data.pop("state_note", None)
    changed: dict[str, list] = {}

    for field, value in data.items():
        if field not in _MUTABLE_FIELDS or value is None:
            continue
        old = getattr(item, field)
        if old != value:
            changed[field] = [
                old.value if hasattr(old, "value") else old,
                value.value if hasattr(value, "value") else value,
            ]
            setattr(item, field, value)

    # Validate against the admin catalogs and serial-uniqueness *after* applying,
    # so the checks see the resulting state (an exception rolls the txn back).
    if "project" in changed or "industry" in changed:
        try:
            catalog_svc.validate_item_catalog(db, item.project, item.industry)
        except catalog_svc.CatalogError as exc:
            raise DomainError(str(exc)) from exc
    if "serial" in changed or "card_type" in changed:
        _check_unique_serial(db, item)

    if manager_ids is not None:
        # Compare before writing. The edit form always sends `manager_ids`, so an
        # unconditional assignment logged "Updated … (manager_ids)" on *every*
        # save — burying real history under identical no-op entries (§10) — and
        # recorded the old value as a useless `None`.
        before = sorted(m.id for m in item.managers)
        after = sorted(set(manager_ids))
        if before != after:
            item.managers = db.query(User).filter(User.id.in_(after)).all()
            changed["manager_ids"] = [before, after]

    if changed:
        record_audit(
            db,
            item=item,
            action="update",
            summary=f"Updated {item.type.value} '{item.name}' ({', '.join(changed)})",
            user=user,
            details={"changed": changed},
        )

    # Last, so a catalog/serial rejection above aborts the whole edit rather
    # than leaving a move behind. `None` means "not supplied" here, matching how
    # every other field in this function treats it.
    if new_state is not None:
        change_state(db, item, new_state, state_note, user)
    if new_location_id is not None and new_location_id != item.location_id:
        move_item(db, item, new_location_id, user)

    return item


# ─────────────────────────── move (cascade) ───────────────────────────
def move_item(
    db: Session, item: Item, location_id: int, user: User, note: str | None = None
) -> Item:
    """Move an item to a new location.

    Cascades *downward* to every descendant — moving a linking item drags all
    of its linked items. Moving a leaf (a linked card) affects nothing else,
    which is exactly the behaviour required by §3.
    """
    old_location = item.location_id
    item.location_id = location_id

    moved_children: list[int] = []
    stack = list(item.children)
    while stack:
        child = stack.pop()
        child.location_id = location_id
        moved_children.append(child.id)
        stack.extend(child.children)

    record_audit(
        db,
        item=item,
        action="move",
        summary=(
            f"Moved {item.type.value} '{item.name}' to location #{location_id}"
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
def link_item(db: Session, child: Item, parent: Item, user: User) -> Item:
    validate_link(child, parent)
    child.parent_id = parent.id
    # Assembled items inherit the container's location — and so does everything
    # already inside the child (§9: a container drags its whole contents).
    cascaded: list[int] = []
    if parent.location_id is not None:
        child.location_id = parent.location_id
        for cid in _descendant_ids(child):
            desc = db.get(Item, cid)
            if desc is not None:
                desc.location_id = parent.location_id
                cascaded.append(cid)
    if child.type == ItemType.card:
        child.storage_status = StorageStatus.assembled
    record_audit(
        db,
        item=child,
        action="link",
        summary=f"Linked {child.type.value} '{child.name}' into '{parent.name}'"
        + (f" (+{len(cascaded)} nested items relocated)" if cascaded else ""),
        user=user,
        details={"parent_id": parent.id, "parent_name": parent.name, "cascaded": cascaded},
    )
    return child


def unlink_item(db: Session, child: Item, user: User) -> Item:
    old_parent = child.parent_id
    child.parent_id = None
    if child.type == ItemType.card:
        child.storage_status = StorageStatus.desiccator
    record_audit(
        db,
        item=child,
        action="unlink",
        summary=f"Unlinked {child.type.value} '{child.name}'",
        user=user,
        details={"previous_parent_id": old_parent},
    )
    return child


# ─────────────────────────── state machine ───────────────────────────
def change_state(
    db: Session, item: Item, new_state: ItemState, note: str | None, user: User
) -> Item:
    old_state = item.state
    if old_state == new_state:
        return item

    # §5/§6/§7 — transitions into or out of "faulty" demand an explanation.
    requires_note = new_state == ItemState.faulty or old_state == ItemState.faulty
    if requires_note and not (note and note.strip()):
        raise DomainError(
            "A note explaining how the fault occurred or was resolved is required "
            "for transitions between 'faulty' and 'working'."
        )

    item.state = new_state
    db.add(
        StateHistory(
            item_id=item.id, state=new_state, note=note, changed_by=user.id
        )
    )
    record_audit(
        db,
        item=item,
        action="state_change",
        summary=f"State of '{item.name}': {old_state.value} → {new_state.value}",
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
        summary=f"Deleted {item.type.value} '{item.name}'",
        user=user,
        details={"type": item.type.value},
    )
    db.delete(item)


# used by the low-stock check to know which card types we care about
TRACKED_CARD_TYPES = (CardType.company, CardType.unique)
