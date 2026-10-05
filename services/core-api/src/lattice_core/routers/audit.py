"""Audit log: the full log, per-item history, "my items", and Excel export (§10)."""

import io
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_viewer
from lattice_core.models import AuditLog, Item, User, item_managers
from lattice_core.schemas import AuditOut

router = APIRouter(prefix="/audit", tags=["audit"])

# Period name → days back (None = all time).
PERIODS: dict[str, int | None] = {
    "day": 1,
    "week": 7,
    "month": 30,
    "half_year": 182,
    "year": 365,
    "all": None,
}
_PERIOD_PATTERN = "^(" + "|".join(PERIODS) + ")$"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _my_item_ids(db: Session, user: User):
    """Items linked to the user: as a manager of the item or as its responsible."""
    managed = select(item_managers.c.item_id).where(item_managers.c.user_id == user.id)
    responsible = select(Item.id).where(Item.responsible_id == user.id)
    return managed.union(responsible)


def _query(
    db: Session,
    user: User,
    *,
    item_id: int | None,
    template_id: int | None,
    period: str,
    mine: bool,
    action: str | None,
    search: str | None,
):
    q = db.query(AuditLog)
    if item_id:
        q = q.filter(AuditLog.item_id == item_id)
    if template_id:
        q = q.filter(AuditLog.template_id == template_id)
    days = PERIODS[period]
    if days is not None:
        q = q.filter(AuditLog.created_at >= datetime.now(UTC) - timedelta(days=days))
    if mine:
        # Only what happened to *my* items — no other items, no account or
        # template administration, and nothing at all if I'm linked to nothing.
        q = q.filter(AuditLog.item_id.in_(_my_item_ids(db, user)))
    if action:
        q = q.filter(AuditLog.action == action)
    if search:
        like = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace(
            "_", "\\_"
        ) + "%"
        q = q.filter(
            or_(
                AuditLog.summary.ilike(like, escape="\\"),
                AuditLog.item_name.ilike(like, escape="\\"),
                AuditLog.user_name.ilike(like, escape="\\"),
            )
        )
    return q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


@router.get("", response_model=list[AuditOut])
def list_audit(
    item_id: int | None = None,
    template_id: int | None = None,
    period: str = Query("all", pattern=_PERIOD_PATTERN),
    mine: bool = False,
    action: str | None = None,
    search: str | None = None,
    limit: int = Query(200, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(require_viewer),
):
    return _query(
        db, user, item_id=item_id, template_id=template_id, period=period, mine=mine,
        action=action, search=search,
    ).limit(limit).all()


@router.get("/my-items", response_model=list[AuditOut])
def my_items_audit(
    period: str = Query("week", pattern=_PERIOD_PATTERN),
    db: Session = Depends(get_db),
    user: User = Depends(require_viewer),
):
    """Changes on the items linked to me (manager or responsible) in a period."""
    return _query(
        db, user, item_id=None, template_id=None, period=period, mine=True,
        action=None, search=None,
    ).all()


@router.get("/export")
def export_audit(
    item_id: int | None = None,
    template_id: int | None = None,
    period: str = Query("all", pattern=_PERIOD_PATTERN),
    mine: bool = False,
    action: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_viewer),
):
    """The same filters as the list, as an Excel workbook."""
    rows = _query(
        db, user, item_id=item_id, template_id=template_id, period=period, mine=mine,
        action=action, search=search,
    ).all()
    wb = Workbook()
    ws = wb.active
    ws.title = "audit"
    headers = ["When (UTC)", "User", "Action", "Item / template", "Summary", "Details"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        when = r.created_at
        if when is not None and when.tzinfo is not None:
            when = when.astimezone(UTC).replace(tzinfo=None)
        ws.append([
            when, r.user_name, r.action, r.item_name, r.summary,
            ", ".join(f"{k}: {v}" for k, v in (r.details or {}).items()),
        ])
    for col, width in zip("ABCDEF", (20, 22, 22, 32, 70, 60), strict=True):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return StreamingResponse(
        io.BytesIO(buf.getvalue()),
        media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="lattice_audit_{stamp}.xlsx"'},
    )
