"""Change-request workflow (requirement §9).

Editors don't mutate data directly — they submit a *proposal* with a reason.
Viewers may propose exactly one kind of change: moving an item to another
location. Managers linked to the affected item (or all managers, if none are
linked) get notified by email + in-app. On approval the very same service
functions that a manager would call directly are executed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from lattice_shared.events import Event, EventType, Recipient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from lattice_core.errors import DomainError
from lattice_core.events import publish_event
from lattice_core.models import (
    ChangeAction,
    ChangeRequest,
    ChangeStatus,
    Item,
    ItemState,
    ItemTemplate,
    Location,
    User,
    UserRole,
)
from lattice_core.schemas import ItemCreate, ItemUpdate, TemplateCreate, TemplateUpdate
from lattice_core.services import items as item_svc
from lattice_core.services import templates as template_svc
from lattice_core.services.audit import record_audit

# What each role may propose. Viewers can ask for a location change only.
_ALLOWED_ACTIONS: dict[UserRole, set[ChangeAction]] = {
    UserRole.viewer: {ChangeAction.move},
    UserRole.editor: set(ChangeAction),
    UserRole.manager: set(ChangeAction),
}

_ITEM_ACTIONS = {
    ChangeAction.update, ChangeAction.delete, ChangeAction.move, ChangeAction.link,
    ChangeAction.unlink, ChangeAction.state_change,
}


def _get_item(db: Session, item_id: int | None) -> Item:
    item = db.get(Item, item_id) if item_id else None
    if item is None:
        raise DomainError(f"Item {item_id} not found")
    return item


def _get_template(db: Session, template_id: int | None) -> ItemTemplate:
    tpl = db.get(ItemTemplate, template_id) if template_id else None
    if tpl is None:
        raise DomainError(f"Template {template_id} not found")
    return tpl


def resolve_managers(db: Session, item: Item | None) -> list[User]:
    """Managers linked to the item, or every manager if the item has none."""
    if item is not None:
        linked = [m for m in item.managers if m.is_active]
        if linked:
            return linked
    return db.query(User).filter(User.role == UserRole.manager, User.is_active).all()


def _auto_description(
    db: Session,
    action: ChangeAction,
    payload: dict,
    target: str | None,
    template: ItemTemplate | None = None,
) -> str:
    """A readable "what" for proposals that didn't spell one out.

    The proposer is asked *why* (the reason) once; *what* is already fully
    described by the action and its payload, so asking for it again was the
    "fill the reason twice" complaint.
    """
    name = f" '{target}'" if target else ""
    if action == ChangeAction.move:
        loc = db.get(Location, payload.get("location_id")) if payload.get("location_id") else None
        return f"Move{name} to {loc.name if loc else 'another location'}"
    if action == ChangeAction.state_change:
        return f"Change the state of{name} to {payload.get('state')}"
    if action == ChangeAction.link:
        parent = db.get(Item, payload.get("parent_id")) if payload.get("parent_id") else None
        return f"Place{name} inside {parent.label if parent else 'another item'}"
    if action == ChangeAction.unlink:
        return f"Take{name} out of its container"
    if action == ChangeAction.delete:
        return f"Delete{name}"
    if action == ChangeAction.create:
        return f"Create a new{name} item"
    if action == ChangeAction.update:
        labels = {f.key: f.label for f in template.fields} if template is not None else {}
        changed = [labels.get(k, k) for k in (payload.get("values") or {})]
        if payload.get("serial"):
            changed.append("serial")
        return f"Edit{name}" + (f" ({', '.join(changed)})" if changed else "")
    if action == ChangeAction.template_create:
        return f"Create the template '{payload.get('name')}'"
    if action == ChangeAction.template_update:
        return f"Edit the template{name}"
    return action.value  # pragma: no cover


# ─────────────────────────── submit ───────────────────────────
def create_change_request(db: Session, data: dict, user: User) -> ChangeRequest:
    action = ChangeAction(data["action"])
    if action not in _ALLOWED_ACTIONS[user.role]:
        raise PermissionError(
            "Viewers can propose a location change only"
            if user.role == UserRole.viewer
            else f"You cannot propose a '{action.value}' change"
        )
    payload = data.get("payload") or {}
    item = db.get(Item, data["item_id"]) if data.get("item_id") else None
    if action in _ITEM_ACTIONS and item is None:
        raise DomainError("This change needs the item it applies to")
    if action == ChangeAction.move and not payload.get("location_id"):
        raise DomainError("Choose the location to move the item to")

    template = None
    if action == ChangeAction.template_update:
        template = _get_template(db, data.get("template_id"))
    elif action == ChangeAction.create:
        template = db.get(ItemTemplate, payload.get("template_id")) if payload.get(
            "template_id"
        ) else None

    if item is not None:
        target = item.label
    elif template is not None:
        target = template.name
    else:
        target = payload.get("name")

    cr = ChangeRequest(
        action=action,
        item_id=item.id if item else None,
        template_id=template.id if template else None,
        item_type=(item.type if item else template.type if template else data.get("item_type")),
        item_name=target,
        payload=payload,
        description=(data.get("description") or "").strip()
        or _auto_description(
            db, action, payload, target, item.template if item is not None else template
        ),
        reason=data["reason"].strip(),
        proposed_by=user.id,
        status=ChangeStatus.pending,
    )
    db.add(cr)
    db.flush()
    record_audit(
        db,
        item=item,
        template=template,
        action="change_request.submit",
        summary=f"{user.full_name} proposed: {cr.description}",
        user=user,
        details={"change_request_id": cr.id, "reason": cr.reason},
    )
    return cr


async def notify_submission(db: Session, cr: ChangeRequest, item: Item | None) -> None:
    managers = resolve_managers(db, item)
    recipients = [Recipient(user_id=m.id, email=m.email, role="manager") for m in managers]
    event = Event(
        type=EventType.CHANGE_REQUEST_SUBMITTED,
        title="New change request awaiting approval",
        body=f"{cr.description}\n\nWhy: {cr.reason}",
        link=f"/change-requests/{cr.id}",
        recipients=recipients,
        payload={
            "change_request_id": cr.id,
            "action": cr.action.value,
            "item_id": cr.item_id,
            "template_id": cr.template_id,
            "item_name": cr.item_name,
        },
    )
    await publish_event(event)


# ─────────────────────────── apply on approval ───────────────────────────
def apply_change_request(db: Session, cr: ChangeRequest, reviewer: User) -> None:
    """Execute an approved proposal.

    `payload` is free-form JSON chosen by the proposer, so it can be missing
    keys or hold the wrong types. Anything it gets wrong is the proposal's
    fault, not the server's — it becomes a DomainError (a 400 the reviewing
    manager can read) instead of a 500.
    """
    try:
        _apply(db, cr, reviewer)
    except DomainError:
        raise
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        raise DomainError(
            f"This proposal's details are not valid for a '{cr.action.value}' change "
            f"({_describe(exc)}). Reject it and ask for a corrected one."
        ) from exc


def _describe(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'payload'}: {e['msg']}"
            for e in exc.errors()[:3]
        )
    if isinstance(exc, KeyError):
        return f"missing '{exc.args[0]}'"
    return str(exc)


def _apply(db: Session, cr: ChangeRequest, reviewer: User) -> None:
    action = cr.action
    payload = cr.payload or {}

    if action == ChangeAction.create:
        item_svc.create_item(db, ItemCreate(**payload).model_dump(), reviewer)
    elif action == ChangeAction.update:
        item = _get_item(db, cr.item_id)
        parsed = ItemUpdate(**payload).model_dump(exclude_unset=True)
        item_svc.update_item(db, item, parsed, reviewer)
    elif action == ChangeAction.move:
        item = _get_item(db, cr.item_id)
        item_svc.move_item(db, item, int(payload["location_id"]), reviewer, payload.get("note"))
    elif action == ChangeAction.state_change:
        item = _get_item(db, cr.item_id)
        item_svc.change_state(db, item, ItemState(payload["state"]), payload.get("note"), reviewer)
    elif action == ChangeAction.link:
        child = _get_item(db, cr.item_id)
        parent = _get_item(db, int(payload["parent_id"]))
        item_svc.link_item(db, child, parent, reviewer)
    elif action == ChangeAction.unlink:
        child = _get_item(db, cr.item_id)
        item_svc.unlink_item(db, child, reviewer, payload.get("location_id"))
    elif action == ChangeAction.delete:
        item_svc.delete_item(db, _get_item(db, cr.item_id), reviewer)
    elif action == ChangeAction.template_create:
        template_svc.create_template(
            db, TemplateCreate(**payload).model_dump(mode="json"), reviewer
        )
    elif action == ChangeAction.template_update:
        tpl = _get_template(db, cr.template_id)
        parsed = TemplateUpdate(**payload).model_dump(mode="json", exclude_unset=True)
        template_svc.update_template(db, tpl, parsed, reviewer)
    else:  # pragma: no cover - exhaustive above
        raise DomainError(f"Unsupported action: {action}")


def decide(
    db: Session, cr: ChangeRequest, reviewer: User, approve: bool, note: str | None
) -> ChangeRequest:
    if cr.status != ChangeStatus.pending:
        raise DomainError("This change request has already been reviewed")

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
        template=(db.get(ItemTemplate, cr.template_id) if cr.template_id else None),
        action=f"change_request.{'approve' if approve else 'reject'}",
        summary=(
            f"{reviewer.full_name} {'approved' if approve else 'rejected'} "
            f"change request #{cr.id}: {cr.description}"
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
            EventType.CHANGE_REQUEST_APPROVED if approved else EventType.CHANGE_REQUEST_REJECTED
        ),
        title=f"Your change request was {'approved' if approved else 'rejected'}",
        body=(
            f"Change request #{cr.id} — {cr.description} — was "
            f"{'approved and applied' if approved else 'rejected'}."
            + (f"\nNote: {cr.review_note}" if cr.review_note else "")
        ),
        link=f"/change-requests/{cr.id}",
        recipients=[Recipient(user_id=proposer.id, email=proposer.email, role=proposer.role.value)],
        payload={"change_request_id": cr.id, "status": cr.status.value},
    )
    await publish_event(event)
