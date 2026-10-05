"""Change-request endpoints — the approval workflow (§9).

Editors may propose any change; viewers may propose a location change only.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from lattice_core.database import get_db
from lattice_core.deps import require_manager, require_viewer
from lattice_core.models import ChangeRequest, ChangeStatus, Item, User
from lattice_core.schemas import ChangeRequestCreate, ChangeRequestOut, ReviewRequest
from lattice_core.services import change_requests as svc

router = APIRouter(prefix="/change-requests", tags=["change-requests"])


def _load(db: Session, cr_id: int) -> ChangeRequest:
    cr = (
        db.query(ChangeRequest)
        .options(joinedload(ChangeRequest.proposer), joinedload(ChangeRequest.reviewer))
        .filter(ChangeRequest.id == cr_id)
        .first()
    )
    if cr is None:
        raise HTTPException(status_code=404, detail="Change request not found")
    return cr


@router.post("", response_model=ChangeRequestOut, status_code=201)
async def submit(
    data: ChangeRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_viewer),
):
    try:
        cr = svc.create_change_request(db, data.model_dump(mode="json"), user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    db.commit()
    db.refresh(cr)
    item = db.get(Item, cr.item_id) if cr.item_id else None
    await svc.notify_submission(db, cr, item)
    return _load(db, cr.id)


@router.get("", response_model=list[ChangeRequestOut])
def list_requests(
    db: Session = Depends(get_db),
    user: User = Depends(require_viewer),
    status: ChangeStatus | None = None,
    mine: bool = False,
):
    q = db.query(ChangeRequest).options(
        joinedload(ChangeRequest.proposer), joinedload(ChangeRequest.reviewer)
    )
    if status:
        q = q.filter(ChangeRequest.status == status)
    if mine:
        q = q.filter(ChangeRequest.proposed_by == user.id)
    return q.order_by(ChangeRequest.created_at.desc(), ChangeRequest.id.desc()).all()


@router.get("/{cr_id}", response_model=ChangeRequestOut)
def get_request(cr_id: int, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return _load(db, cr_id)


@router.post("/{cr_id}/approve", response_model=ChangeRequestOut)
async def approve(
    cr_id: int,
    body: ReviewRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    cr = _load(db, cr_id)
    try:
        svc.decide(db, cr, user, approve=True, note=(body.note if body else None))
    except Exception:
        db.rollback()
        raise
    db.commit()
    db.refresh(cr)
    await svc.notify_decision(db, cr)
    return _load(db, cr.id)


@router.post("/{cr_id}/reject", response_model=ChangeRequestOut)
async def reject(
    cr_id: int,
    body: ReviewRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    cr = _load(db, cr_id)
    try:
        svc.decide(db, cr, user, approve=False, note=(body.note if body else None))
    except Exception:
        db.rollback()
        raise
    db.commit()
    db.refresh(cr)
    await svc.notify_decision(db, cr)
    return _load(db, cr.id)
