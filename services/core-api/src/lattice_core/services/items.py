"""Item lifecycle: create / update / move / link / unlink / state / delete.

These functions are the single source of truth for mutations. They are called
directly by managers and indirectly (after approval) by the change-request
executor, so the rules live in exactly one place.
"""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from lattice_core.models import (
    SERIAL_TRACKED_CARD_TYPES,
    CardTracking,
    Item,
    ItemState,
    ItemType,
    StateHistory,
    StorageStatus,
    User,
    card_tracking,
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
    """A serial identifies exactly one physical unit, system-wide (§2/§12)."""
    if not item.serial or item.is_template:
        return
    clash = (
        db.query(Item)
        .filter(
            Item.serial == item.serial,
            Item.id != (item.id or -1),
            Item.is_template.is_(False),
        )
        .first()
    )
    if clash:
        raise DomainError(
            f"Serial '{item.serial}' is already used by {clash.type.value} "
            f"'{clash.name}' (#{clash.id})"
        )


def _enforces_unique_name(item: Item) -> bool:
    """Whether this item competes for its name.

    Serial-tracked cards are deliberately exempt: twenty boards off one
    production run are twenty rows of the *same model*, told apart by serial —
    there the name describes the model, not the individual. Everything else
    (setups, assemblies, quantity-tracked commercial cards) is one row per real
    thing, so its name has to identify it unambiguously. Templates are blueprints
    rather than physical items and never take part.
    """
    if item.is_template:
        return False
    if item.type == ItemType.card:
        return card_tracking(item.card_type) is not CardTracking.serial
    return True


def _check_unique_name(db: Session, item: Item) -> None:
    """No two live items may share a name (compared trimmed, case-insensitively)."""
    if not _enforces_unique_name(item):
        return
    normalised = (item.name or "").strip().lower()
    if not normalised:
        return
    clash = (
        db.query(Item)
        .filter(
            func.lower(func.trim(Item.name)) == normalised,
            Item.id != (item.id or -1),
            Item.is_template.is_(False),
            # The exemption above cuts both ways: a batch of serialised boards
            # must not block a setup (or a commercial card) from taking a name.
            or_(
                Item.type != ItemType.card,
                Item.card_type.is_(None),
                Item.card_type.notin_(SERIAL_TRACKED_CARD_TYPES),
            ),
        )
        .first()
    )
    if clash:
        raise DomainError(
            f"The name '{item.name.strip()}' is already used by {clash.type.value} "
            f"'{clash.name}' (#{clash.id}). Names must be unique."
        )


def _enforce_card_rules(db: Session, item: Item, supplied: set[str]) -> None:
    """Keep the two kinds of card honest (§2/§12).

    A commercial card is a quantity of interchangeable parts on one row; a
    company/unique card is one row per physical unit, identified by its serial.
    Values the caller actually sent that contradict its card type are rejected
    with an explanation; leftovers from a card type *change* are normalised
    silently, since a PATCH cannot clear a field by sending ``null``.
    """
    if item.type != ItemType.card:
        item.quantity = 1
        return

    tracking = card_tracking(item.card_type)
    if tracking is None:
        raise DomainError(
            "A card must have a card type (commercial / company / unique) — it "
            "decides whether the card is counted by quantity or by serial."
        )

    if tracking is CardTracking.quantity:
        if "serial" in supplied and (item.serial or "").strip():
            raise DomainError(
                "A commercial card is counted by quantity, not per unit: leave "
                "the serial empty and set the quantity instead."
            )
        item.serial = None
        if item.quantity is None:
            item.quantity = 1
        if item.quantity < 1:
            raise DomainError("Quantity must be at least 1.")
        return

    # Serial-tracked: one row *is* one unit, so the quantity column is pinned.
    if "quantity" in supplied and (item.quantity or 1) != 1:
        raise DomainError(
            f"A {item.card_type.value} card is tracked per unit — add one card "
            "per physical board (each with its own serial) instead of a quantity."
        )
    item.quantity = 1
    item.serial = (item.serial or "").strip() or None
    if item.serial is None and not item.is_template:
        raise DomainError(
            f"A {item.card_type.value} card must have a serial — it identifies "
            "the individual board. Use a commercial card for quantity-only stock."
        )
    _check_unique_serial(db, item)


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
    item.name = (item.name or "").strip()
    _enforce_card_rules(db, item, supplied=set(data))
    _check_unique_name(db, item)

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
    "serial", "storage_status", "quantity",
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
        if field == "name":
            value = value.strip()
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
    # Always re-checked, not just when a card field moved: switching card_type
    # is what strands a serial on a quantity card (or a quantity on a serialised
    # one), and the check is the only place that cleans it up. Whatever it
    # normalises is folded back into `changed` so the audit log tells the whole
    # story rather than showing a serial that silently vanished (§10).
    before = {"serial": item.serial, "quantity": item.quantity}
    _enforce_card_rules(db, item, supplied=set(data))
    for field, old in before.items():
        new = getattr(item, field)
        if old == new:
            continue
        changed.setdefault(field, [old, new])[1] = new

    if "name" in changed or "card_type" in changed:
        _check_unique_name(db, item)

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

    Cascades *downward* to every descendant — moving a container drags all of
    its contents (§3). A **linked item cannot be moved on its own**: being
    linked means it physically sits inside its parent, so it is wherever the
    parent is. The only honest way to relocate it is to move the parent, or to
    unlink it first — and the error says which (§3).
    """
    if item.parent_id is not None:
        parent = db.get(Item, item.parent_id)
        where = (
            f"{parent.type.value} '{parent.name}' (#{parent.id})"
            if parent is not None
            else f"item #{item.parent_id}"
        )
        raise DomainError(
            f"'{item.name}' sits inside {where}, so it has no location of its "
            f"own. Move {where} instead — everything inside it follows — or "
            f"unlink '{item.name}' first if it has physically come out."
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


def set_children(db: Session, parent: Item, child_ids: list[int], user: User) -> Item:
    """Make the parent's contents exactly ``child_ids`` (§6/§8).

    Contents could only be chosen while *creating* a container, which left no
    way to correct a setup after the fact. Everything is validated before
    anything is written, so a bad id can't leave the tree half-edited, and the
    add/remove both go through link/unlink — the cascade and the audit trail
    behave exactly as they do anywhere else.
    """
    if parent.is_template:
        raise DomainError("Templates cannot take part in the hierarchy")

    desired = list(dict.fromkeys(child_ids))
    current = {c.id for c in parent.children}

    to_add: list[Item] = []
    for cid in desired:
        if cid in current:
            continue
        child = db.get(Item, cid)
        if child is None:
            raise DomainError(f"Item {cid} not found")
        validate_link(child, parent)
        to_add.append(child)
    # Snapshot: unlinking mutates `parent.children` as we walk it.
    to_remove = [c for c in list(parent.children) if c.id not in set(desired)]

    for child in to_remove:
        unlink_item(db, child, user)
    for child in to_add:
        link_item(db, child, parent, user)

    if to_add or to_remove:
        record_audit(
            db,
            item=parent,
            action="update",
            summary=(
                f"Updated contents of {parent.type.value} '{parent.name}' "
                f"(+{len(to_add)} / -{len(to_remove)})"
            ),
            user=user,
            details={
                "added": [c.id for c in to_add],
                "removed": [c.id for c in to_remove],
            },
        )
    return parent


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
