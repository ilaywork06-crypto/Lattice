"""Audit-log helper (requirement §10 — change history)."""

from sqlalchemy.orm import Session

from lattice_core.models import AuditLog, Item, ItemTemplate, User


def record_audit(
    db: Session,
    *,
    action: str,
    summary: str,
    user: User | None,
    item: Item | None = None,
    template: ItemTemplate | None = None,
    details: dict | None = None,
) -> AuditLog:
    if template is None and item is not None:
        template = item.template
    if item is not None:
        name = item.label
    elif template is not None:
        name = template.name
    else:
        name = None
    entry = AuditLog(
        item_id=item.id if item else None,
        template_id=template.id if template else None,
        item_name=name,
        action=action,
        summary=summary,
        details=details or {},
        user_id=user.id if user else None,
        user_name=user.full_name if user else None,
    )
    db.add(entry)
    return entry
