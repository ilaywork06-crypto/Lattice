"""Audit-log helper (requirement §10 — per-item change history)."""

from sqlalchemy.orm import Session

from lattice_core.models import AuditLog, Item, User


def record_audit(
    db: Session,
    *,
    action: str,
    summary: str,
    user: User | None,
    item: Item | None = None,
    details: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        item_id=item.id if item else None,
        item_name=item.name if item else None,
        action=action,
        summary=summary,
        details=details or {},
        user_id=user.id if user else None,
        user_name=user.full_name if user else None,
    )
    db.add(entry)
    return entry
