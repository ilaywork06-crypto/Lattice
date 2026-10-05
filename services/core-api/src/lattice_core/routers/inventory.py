"""Inventory, desiccator stock and low-stock thresholds."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_editor, require_manager, require_viewer
from lattice_core.models import CardType, ItemTemplate, ItemType, StockThreshold, User
from lattice_core.schemas import (
    InventoryGroup,
    InventorySummary,
    ThresholdCreate,
    ThresholdOut,
)
from lattice_core.services import inventory as svc

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("/summary", response_model=InventorySummary)
def summary(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return svc.summary(db)


@router.get("/cards", response_model=list[InventoryGroup])
def card_stock(
    card_type: CardType | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    return svc.card_groups(db, card_type)


@router.get("/desiccator", response_model=list[InventoryGroup])
def desiccator(
    card_type: CardType | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    """Only the templates with stock actually sitting in the desiccator."""
    return [g for g in svc.card_groups(db, card_type) if g.desiccator > 0]


@router.get("/thresholds", response_model=list[ThresholdOut])
def list_thresholds(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return svc.threshold_status(db)


@router.get("/low-stock", response_model=list[ThresholdOut])
def low_stock(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return svc.low_stock(db)


@router.post("/thresholds", response_model=ThresholdOut, status_code=201)
async def create_threshold(
    data: ThresholdCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
):
    """Set (or replace) the minimum available stock of one card template."""
    tpl = db.get(ItemTemplate, data.template_id)
    if tpl is None or tpl.type != ItemType.card:
        raise HTTPException(status_code=400, detail="Pick a card template to set a threshold on.")
    t = db.query(StockThreshold).filter(StockThreshold.template_id == tpl.id).first()
    if t is None:
        t = StockThreshold(template_id=tpl.id)
        db.add(t)
    t.min_quantity = data.min_quantity
    t.editor_email = data.editor_email
    db.commit()
    db.refresh(t)
    await svc.check_and_alert_low_stock(db)
    return svc.threshold_out(db, t)


@router.delete("/thresholds/{threshold_id}", status_code=204)
def delete_threshold(
    threshold_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    t = db.get(StockThreshold, threshold_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Threshold not found")
    db.delete(t)
    db.commit()
