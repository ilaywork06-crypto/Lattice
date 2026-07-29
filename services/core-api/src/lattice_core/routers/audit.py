"""Audit log endpoints: per-item history and the manager's linked-items log (§10)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_manager, require_viewer
from lattice_core.models import AuditLog, User, item_managers
from lattice_core.schemas import AuditOut

router = APIRouter(prefix="/audit", tags=["audit"])

_PERIODS = {"day": 1, "week": 7, "month": 30}


@router.get("", response_model=list[AuditOut])
def list_audit(
    item_id: int | None = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    q = db.query(AuditLog)
    if item_id:
        q = q.filter(AuditLog.item_id == item_id)
    return q.order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/my-items", response_model=list[AuditOut])
def my_items_audit(
    period: str = Query("week", pattern="^(day|week|month)$"),
    db: Session = Depends(get_db),
    manager: User = Depends(require_manager),
):
    """All changes on items linked to the current manager within a period (§10)."""
    since = datetime.now(UTC) - timedelta(days=_PERIODS[period])
    linked_item_ids = [
        row[0]
        for row in db.query(item_managers.c.item_id)
        .filter(item_managers.c.user_id == manager.id)
        .all()
    ]
    q = db.query(AuditLog).filter(AuditLog.created_at >= since)
    if linked_item_ids:
        q = q.filter(AuditLog.item_id.in_(linked_item_ids))
    else:
        # Manager owns nothing specific → show everything in the period.
        pass
    return q.order_by(AuditLog.created_at.desc()).all()
