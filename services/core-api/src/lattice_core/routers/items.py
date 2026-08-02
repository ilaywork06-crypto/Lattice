"""Items: setups, assemblies and cards — reads for everyone, direct mutations
for managers. Editors mutate through /change-requests instead (see §8/§9)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload, selectinload

from lattice_core.database import get_db
from lattice_core.deps import require_manager, require_viewer
from lattice_core.models import (
    CardType,
    Document,
    ExtraItem,
    Item,
    ItemState,
    ItemType,
    StorageStatus,
    User,
)
from lattice_core.schemas import (
    BulkAction,
    BulkRequest,
    BulkResult,
    DocumentCreate,
    DocumentOut,
    ExtraItemCreate,
    ExtraItemOut,
    ItemCreate,
    ItemListOut,
    ItemOut,
    ItemUpdate,
    LinkRequest,
    MoveRequest,
    StateChangeRequest,
)
from lattice_core.services import inventory as inv_svc
from lattice_core.services import items as svc

router = APIRouter(prefix="/items", tags=["items"])


def _get(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


async def _maybe_alert_low_stock(db: Session, item: Item) -> None:
    if item.type == ItemType.card:
        await inv_svc.check_and_alert_low_stock(db)


# ─────────────────────────── reads ───────────────────────────
@router.get("", response_model=list[ItemListOut])
def list_items(
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
    type: ItemType | None = None,
    state: ItemState | None = None,
    card_type: CardType | None = None,
    storage_status: StorageStatus | None = None,
    project: str | None = None,
    industry: str | None = None,
    location_id: int | None = None,
    unassigned: bool | None = Query(None, description="Only items without a parent"),
    templates: bool = Query(False, description="Return templates instead of live items"),
    search: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    q = db.query(Item).options(
        joinedload(Item.location),
        selectinload(Item.managers),
        selectinload(Item.children),
    )
    # Templates live in their own space and never mix with live items.
    q = q.filter(Item.is_template.is_(bool(templates)))
    if type:
        q = q.filter(Item.type == type)
    if state:
        q = q.filter(Item.state == state)
    if card_type:
        q = q.filter(Item.card_type == card_type)
    if storage_status:
        q = q.filter(Item.storage_status == storage_status)
    if project:
        q = q.filter(Item.project == project)
    if industry:
        q = q.filter(Item.industry == industry)
    if location_id:
        q = q.filter(Item.location_id == location_id)
    if unassigned:
        q = q.filter(Item.parent_id.is_(None))
    if search:
        # Escape LIKE wildcards so a literal % or _ in the box doesn't match rows
        # it shouldn't (see routers/search.py:_like).
        like = "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        q = q.filter(
            or_(
                Item.name.ilike(like, escape="\\"),
                Item.serial.ilike(like, escape="\\"),
            )
        )

    items = q.order_by(Item.type, Item.name).offset(offset).limit(limit).all()
    return [
        ItemListOut(
            id=i.id,
            type=i.type,
            name=i.name,
            industry=i.industry,
            project=i.project,
            team=i.team,
            state=i.state,
            card_type=i.card_type,
            version=i.version,
            serial=i.serial,
            quantity=i.quantity,
            storage_status=i.storage_status,
            parent_id=i.parent_id,
            location_id=i.location_id,
            location_name=i.location.name if i.location else None,
            children_count=len(i.children),
            is_template=i.is_template,
            manager_names=[m.full_name for m in i.managers],
            updated_at=i.updated_at,
        )
        for i in items
    ]


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    item = (
        db.query(Item)
        .options(
            joinedload(Item.location),
            joinedload(Item.parent),
            selectinload(Item.children),
            selectinload(Item.managers),
            selectinload(Item.state_history),
            selectinload(Item.documents),
            selectinload(Item.extra_items),
        )
        .filter(Item.id == item_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


# ─────────────────────── direct mutations (manager) ───────────────────────
@router.post("", response_model=ItemOut, status_code=201)
async def create_item(
    data: ItemCreate, db: Session = Depends(get_db), user: User = Depends(require_manager)
):
    try:
        item = svc.create_item(db, data.model_dump(), user)
    except svc.DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    db.refresh(item)
    await _maybe_alert_low_stock(db, item)
    return get_item(item.id, db, user)


@router.patch("/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: int,
    data: ItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    item = _get(db, item_id)
    svc.update_item(db, item, data.model_dump(exclude_unset=True), user)
    db.commit()
    # Editing a commercial card's quantity is now *the* way stock goes down, so
    # a plain PATCH has to be able to trip the alert — creates and deletes alone
    # no longer see every change to the numbers.
    await _maybe_alert_low_stock(db, item)
    return get_item(item_id, db, user)


@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager)
):
    item = _get(db, item_id)
    is_card = item.type == ItemType.card
    svc.delete_item(db, item, user)
    db.commit()
    if is_card:
        await inv_svc.check_and_alert_low_stock(db)


@router.post("/{item_id}/move", response_model=ItemOut)
async def move_item(
    item_id: int,
    body: MoveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    item = _get(db, item_id)
    svc.move_item(db, item, body.location_id, user, body.note)
    db.commit()
    return get_item(item_id, db, user)


@router.post("/{item_id}/link", response_model=ItemOut)
async def link_item(
    item_id: int,
    body: LinkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    child = _get(db, item_id)
    parent = _get(db, body.parent_id)
    try:
        svc.link_item(db, child, parent, user)
    except svc.DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return get_item(item_id, db, user)


@router.post("/{item_id}/unlink", response_model=ItemOut)
async def unlink_item(
    item_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager)
):
    child = _get(db, item_id)
    svc.unlink_item(db, child, user)
    db.commit()
    return get_item(item_id, db, user)


@router.post("/{item_id}/state", response_model=ItemOut)
async def change_state(
    item_id: int,
    body: StateChangeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    item = _get(db, item_id)
    try:
        svc.change_state(db, item, body.state, body.note, user)
    except svc.DomainError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return get_item(item_id, db, user)


# ─────────────────────────── bulk operations ───────────────────────────
@router.post("/bulk", response_model=BulkResult)
async def bulk_action(
    body: BulkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Apply one action to many items atomically (§5 convenience at scale).

    The whole batch succeeds or fails together, so a partial/inconsistent state
    can never be left behind (§10 reliability).
    """
    ids = list(dict.fromkeys(body.item_ids))  # dedupe, keep order
    items = {i.id: i for i in db.query(Item).filter(Item.id.in_(ids)).all()}
    missing = [i for i in ids if i not in items]
    if missing:
        raise HTTPException(status_code=404, detail=f"Items not found: {missing}")

    touched_card = False
    try:
        for iid in ids:
            item = items[iid]
            touched_card = touched_card or item.type == ItemType.card
            if body.action == BulkAction.move:
                if body.location_id is None:
                    raise svc.DomainError("location_id is required for a bulk move")
                svc.move_item(db, item, body.location_id, user, body.note)
            elif body.action == BulkAction.state_change:
                if body.state is None:
                    raise svc.DomainError("state is required for a bulk state change")
                svc.change_state(db, item, body.state, body.note, user)
            elif body.action == BulkAction.unlink:
                svc.unlink_item(db, item, user)
            elif body.action == BulkAction.link:
                if body.parent_id is None:
                    raise svc.DomainError("parent_id is required for a bulk link")
                parent = _get(db, body.parent_id)
                svc.link_item(db, item, parent, user)
            elif body.action == BulkAction.delete:
                svc.delete_item(db, item, user)
    except svc.DomainError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        db.rollback()
        raise

    db.commit()
    if touched_card:
        await inv_svc.check_and_alert_low_stock(db)
    return BulkResult(processed=len(ids))


# ─────────────────────── documents & extras ───────────────────────
@router.post("/{item_id}/documents", response_model=DocumentOut, status_code=201)
def add_document(
    item_id: int,
    body: DocumentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    _get(db, item_id)
    doc = Document(item_id=item_id, **body.model_dump())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{item_id}/documents/{doc_id}", status_code=204)
def delete_document(
    item_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    doc = db.get(Document, doc_id)
    if doc is None or doc.item_id != item_id:
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()


@router.post("/{item_id}/extras", response_model=ExtraItemOut, status_code=201)
def add_extra(
    item_id: int,
    body: ExtraItemCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    item = _get(db, item_id)
    if item.type != ItemType.setup:
        raise HTTPException(status_code=400, detail="Extra items belong to setups only")
    extra = ExtraItem(setup_id=item_id, **body.model_dump())
    db.add(extra)
    db.commit()
    db.refresh(extra)
    return extra


@router.delete("/{item_id}/extras/{extra_id}", status_code=204)
def delete_extra(
    item_id: int,
    extra_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    extra = db.get(ExtraItem, extra_id)
    if extra is None or extra.setup_id != item_id:
        raise HTTPException(status_code=404, detail="Extra item not found")
    db.delete(extra)
    db.commit()
