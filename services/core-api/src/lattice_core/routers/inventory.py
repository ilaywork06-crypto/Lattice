"""Inventory, desiccator stock and low-stock thresholds (§7, §12)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_editor, require_manager, require_viewer
from lattice_core.models import CardType, Item, ItemType, StockThreshold, User
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
    """Only the groups actually holding stock in the desiccator (§12).

    The condition used to be `g.desiccator > 0 or g.total > 0`; a group only
    exists when it has at least one card, so `total > 0` was always true and the
    whole filter passed everything through — making this endpoint a duplicate of
    /inventory/cards and the UI's All/Desiccator toggle do nothing.
    """
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
    """Set a minimum on the model of an **existing** card.

    The group is derived from that card rather than typed in, so a threshold can
    never watch a name nobody stocks (and so its alerts can link to a real card).
    """
    item = db.get(Item, data.item_id)
    if item is None or item.type != ItemType.card or item.is_template:
        raise HTTPException(
            status_code=400,
            detail="Pick an existing card to set a stock threshold on.",
        )
    if item.card_type is None:
        raise HTTPException(
            status_code=400, detail=f"Card '{item.name}' has no card type."
        )

    version = None if data.any_version else item.version
    clash = (
        db.query(StockThreshold)
        .filter(
            StockThreshold.card_type == item.card_type,
            StockThreshold.name == item.name,
            StockThreshold.version.is_(None) if version is None
            else StockThreshold.version == version,
        )
        .first()
    )
    if clash:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A threshold already watches '{item.name}'"
                + (f" v{version}" if version else " (all versions)")
                + " — edit or remove that one instead of adding a second."
            ),
        )

    t = StockThreshold(
        item_id=item.id,
        card_type=item.card_type,
        name=item.name,
        version=version,
        min_quantity=data.min_quantity,
        editor_email=data.editor_email,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    await svc.check_and_alert_low_stock(db)
    for status in svc.threshold_status(db):
        if status.id == t.id:
            return status
    raise HTTPException(status_code=500, detail="Threshold not found after create")


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
