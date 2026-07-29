"""Change-request workflow (requirement §9).

Editors don't mutate data directly — they submit a *proposal* describing the
change and the reason. Managers linked to the affected item (or all managers, if
none are linked) get notified by email + in-app. On approval the very same
service functions that a manager would call directly are executed.
"""

from __future__ import annotations

from datetime import UTC

from lattice_shared.events import Event, EventType, Recipient
from sqlalchemy.orm import Session

from lattice_core.events import publish_event
from lattice_core.models import (
    ChangeAction,
    ChangeRequest,
    ChangeStatus,
    Item,
    ItemState,
    User,
    UserRole,
)
from lattice_core.schemas import ItemCreate, ItemUpdate
from lattice_core.services import items as item_svc
from lattice_core.services.audit import record_audit


def _get_item(db: Session, item_id: int | None) -> Item:
    item = db.get(Item, item_id) if item_id else None
    if item is None:
        raise item_svc.DomainError(f"Item {item_id} not found")
    return item


def resolve_managers(db: Session, item: Item | None) -> list[User]:
    """Managers linked to the item, or every manager if the item has none."""
    if item is not None and item.managers:
        return list(item.managers)
    return db.query(User).filter(User.role == UserRole.manager, User.is_active).all()


# ─────────────────────────── submit ───────────────────────────
def create_change_request(db: Session, data: dict, user: User) -> ChangeRequest:
    item = db.get(Item, data["item_id"]) if data.get("item_id") else None
    cr = ChangeRequest(
        action=ChangeAction(data["action"]),
        item_id=data.get("item_id"),
        item_type=(item.type if item else data.get("item_type")),
        item_name=(item.name if item else (data.get("payload") or {}).get("name")),
        payload=data.get("payload") or {},
        description=data["description"],
        reason=data["reason"],
        proposed_by=user.id,
        status=ChangeStatus.pending,
    )
    db.add(cr)
    db.flush()
    record_audit(
        db,
        item=item,
        action="change_request.submit",
        summary=f"{user.full_name} proposed a '{cr.action.value}' change",
        user=user,
        details={"change_request_id": cr.id, "reason": cr.reason},
    )
    return cr


async def notify_submission(db: Session, cr: ChangeRequest, item: Item | None) -> None:
    managers = resolve_managers(db, item)
    recipients = [
        Recipient(user_id=m.id, email=m.email, role="manager") for m in managers
    ]
    target = f" for '{cr.item_name}'" if cr.item_name else ""
    event = Event(
        type=EventType.CHANGE_REQUEST_SUBMITTED,
        title="New change request awaiting approval",
        body=(
            f"A '{cr.action.value}' change{target} was proposed.\n\n"
            f"What: {cr.description}\nWhy: {cr.reason}"
        ),
        link=f"/change-requests/{cr.id}",
        recipients=recipients,
        payload={
            "change_request_id": cr.id,
            "action": cr.action.value,
            "item_id": cr.item_id,
            "item_name": cr.item_name,
        },
    )
    await publish_event(event)


# ─────────────────────────── apply on approval ───────────────────────────
def apply_change_request(db: Session, cr: ChangeRequest, reviewer: User) -> None:
    action = cr.action
    payload = cr.payload or {}

    if action == ChangeAction.create:
        parsed = ItemCreate(**payload)
        item_svc.create_item(db, parsed.model_dump(), reviewer)

    elif action == ChangeAction.update:
        item = _get_item(db, cr.item_id)
        parsed = ItemUpdate(**payload).model_dump(exclude_unset=True)
        item_svc.update_item(db, item, parsed, reviewer)

    elif action == ChangeAction.move:
        item = _get_item(db, cr.item_id)
        item_svc.move_item(
            db, item, int(payload["location_id"]), reviewer, payload.get("note")
        )

    elif action == ChangeAction.state_change:
        item = _get_item(db, cr.item_id)
        item_svc.change_state(
            db, item, ItemState(payload["state"]), payload.get("note"), reviewer
        )

    elif action == ChangeAction.link:
        child = _get_item(db, cr.item_id)
        parent = _get_item(db, int(payload["parent_id"]))
        item_svc.link_item(db, child, parent, reviewer)

    elif action == ChangeAction.unlink:
        child = _get_item(db, cr.item_id)
        item_svc.unlink_item(db, child, reviewer)

    elif action == ChangeAction.delete:
        item = _get_item(db, cr.item_id)
        item_svc.delete_item(db, item, reviewer)

    else:  # pragma: no cover - exhaustive above
        raise item_svc.DomainError(f"Unsupported action: {action}")


def decide(
    db: Session, cr: ChangeRequest, reviewer: User, approve: bool, note: str | None
) -> ChangeRequest:
    from datetime import datetime

    if cr.status != ChangeStatus.pending:
        raise item_svc.DomainError("This change request has already been reviewed")

    if approve:
        apply_change_request(db, cr, reviewer)
        cr.status = ChangeStatus.approved
    else:
        cr.status = ChangeStatus.rejected

    cr.reviewed_by = reviewer.id
    cr.review_note = note
    cr.reviewed_at = datetime.now(UTC)

    record_audit(
        db,
        item=(db.get(Item, cr.item_id) if cr.item_id else None),
        action=f"change_request.{'approve' if approve else 'reject'}",
        summary=(
            f"{reviewer.full_name} {'approved' if approve else 'rejected'} "
            f"change request #{cr.id}"
        ),
        user=reviewer,
        details={"change_request_id": cr.id, "note": note},
    )
    return cr


async def notify_decision(db: Session, cr: ChangeRequest) -> None:
    proposer = db.get(User, cr.proposed_by)
    if proposer is None:
        return
    approved = cr.status == ChangeStatus.approved
    event = Event(
        type=(
            EventType.CHANGE_REQUEST_APPROVED
            if approved
            else EventType.CHANGE_REQUEST_REJECTED
        ),
        title=f"Your change request was {'approved' if approved else 'rejected'}",
        body=(
            f"Change request #{cr.id} ({cr.action.value}) for "
            f"'{cr.item_name or 'new item'}' was "
            f"{'approved and applied' if approved else 'rejected'}."
            + (f"\nNote: {cr.review_note}" if cr.review_note else "")
        ),
        link=f"/change-requests/{cr.id}",
        recipients=[Recipient(user_id=proposer.id, email=proposer.email, role="editor")],
        payload={"change_request_id": cr.id, "status": cr.status.value},
    )
    await publish_event(event)
