"""Items: setups, assemblies and cards — reads for everyone, direct mutations
for managers. Editors (and, for moves, viewers) mutate through /change-requests.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from lattice_core.database import get_db
from lattice_core.deps import require_manager, require_viewer
from lattice_core.errors import DomainError
from lattice_core.models import (
    CardType,
    Document,
    ExtraItem,
    Item,
    ItemState,
    ItemTemplate,
    ItemType,
    Location,
    StorageStatus,
    User,
    template_children,
)
from lattice_core.schemas import (
    BulkAction,
    BulkRequest,
    BulkResult,
    ChildrenRequest,
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
    UnlinkRequest,
)
from lattice_core.services import files as files_svc
from lattice_core.services import inventory as inv_svc
from lattice_core.services import items as svc
from lattice_core.services import views

router = APIRouter(prefix="/items", tags=["items"])


def _get(db: Session, item_id: int) -> Item:
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def _maybe_alert_low_stock(db: Session, *items: Item) -> None:
    # A container carries its cards with it (in or out of the desiccator), so
    # anything that is or holds a card can change the available stock.
    if any(i.type == ItemType.card or i.children for i in items):
        await inv_svc.check_and_alert_low_stock(db)


# ─────────────────────────── reads ───────────────────────────
@router.get("", response_model=list[ItemListOut])
def list_items(
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
    type: ItemType | None = None,
    template_id: int | None = None,
    state: ItemState | None = None,
    card_type: CardType | None = None,
    storage_status: StorageStatus | None = None,
    location_id: int | None = None,
    parent_id: int | None = None,
    unassigned: bool | None = Query(None, description="Only items without a parent"),
    include_destroyed: bool = True,
    child_of_template: int | None = Query(
        None, description="Items whose template may be placed inside this template"
    ),
    parent_of_template: int | None = Query(
        None, description="Items whose template may contain this template"
    ),
    search: str | None = None,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    q = (
        db.query(Item)
        .join(Item.template)
        .options(
            joinedload(Item.template),
            joinedload(Item.location),
            joinedload(Item.parent).joinedload(Item.template),
            joinedload(Item.industry),
            joinedload(Item.project),
            joinedload(Item.team),
            selectinload(Item.managers),
            selectinload(Item.children),
        )
    )
    if type:
        q = q.filter(Item.type == type)
    if template_id:
        q = q.filter(Item.template_id == template_id)
    if state:
        q = q.filter(Item.state == state)
    if not include_destroyed:
        q = q.filter(Item.state != ItemState.destroyed)
    if card_type:
        q = q.filter(ItemTemplate.card_type == card_type)
    if location_id:
        q = q.filter(Item.location_id == location_id)
    if parent_id:
        q = q.filter(Item.parent_id == parent_id)
    if unassigned:
        q = q.filter(Item.parent_id.is_(None))
    if storage_status:
        # Mirrors Item.storage_status: the desiccator is a place, so it wins over
        # being assembled.
        q = q.filter(Item.type == ItemType.card).outerjoin(
            Location, Item.location_id == Location.id
        )
        in_desiccator = Location.is_desiccator.is_(True)
        outside = or_(Location.id.is_(None), Location.is_desiccator.is_(False))
        if storage_status == StorageStatus.desiccator:
            q = q.filter(in_desiccator)
        elif storage_status == StorageStatus.assembled:
            q = q.filter(Item.parent_id.is_not(None), outside)
        else:
            q = q.filter(Item.parent_id.is_(None), outside)
    if child_of_template:
        q = q.join(
            template_children,
            and_(
                template_children.c.child_template_id == Item.template_id,
                template_children.c.parent_template_id == child_of_template,
            ),
        )
    if parent_of_template:
        q = q.join(
            template_children,
            and_(
                template_children.c.parent_template_id == Item.template_id,
                template_children.c.child_template_id == parent_of_template,
            ),
        )
    if search:
        like = _like(search.strip())
        q = q.filter(
            or_(
                ItemTemplate.name.ilike(like, escape="\\"),
                Item.serial.ilike(like, escape="\\"),
            )
        )
    items = q.order_by(Item.type, ItemTemplate.name, Item.serial).offset(offset).limit(limit).all()
    return [views.item_list_out(i) for i in items]


@router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return views.item_out(db, _get(db, item_id))


# ─────────────────────── direct mutations (manager) ───────────────────────
@router.post("", response_model=ItemOut, status_code=201)
async def create_item(
    data: ItemCreate, db: Session = Depends(get_db), user: User = Depends(require_manager)
):
    item = svc.create_item(db, data.model_dump(), user)
    db.commit()
    db.refresh(item)
    await _maybe_alert_low_stock(db, item)
    return views.item_out(db, item)


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
    db.refresh(item)
    await _maybe_alert_low_stock(db, item)
    return views.item_out(db, item)


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
    db.refresh(item)
    # Moving cards in or out of the desiccator changes available stock.
    await _maybe_alert_low_stock(db, item)
    return views.item_out(db, item)


@router.post("/{item_id}/link", response_model=ItemOut)
async def link_item(
    item_id: int,
    body: LinkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    child = _get(db, item_id)
    parent = _get(db, body.parent_id)
    svc.link_item(db, child, parent, user)
    db.commit()
    db.refresh(child)
    await _maybe_alert_low_stock(db, child)
    return views.item_out(db, child)


@router.put("/{item_id}/children", response_model=ItemOut)
async def set_children(
    item_id: int,
    body: ChildrenRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Replace a container's contents — the counterpart to `child_ids` on
    create, so a setup or assembly stays editable after it exists."""
    parent = _get(db, item_id)
    svc.set_children(db, parent, body.child_ids, user)
    db.commit()
    db.refresh(parent)
    await inv_svc.check_and_alert_low_stock(db)
    return views.item_out(db, parent)


@router.post("/{item_id}/unlink", response_model=ItemOut)
async def unlink_item(
    item_id: int,
    body: UnlinkRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    child = _get(db, item_id)
    svc.unlink_item(db, child, user, body.location_id if body else None)
    db.commit()
    db.refresh(child)
    await _maybe_alert_low_stock(db, child)
    return views.item_out(db, child)


@router.post("/{item_id}/state", response_model=ItemOut)
async def change_state(
    item_id: int,
    body: StateChangeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    item = _get(db, item_id)
    svc.change_state(db, item, body.state, body.note, user)
    db.commit()
    db.refresh(item)
    await _maybe_alert_low_stock(db, item)
    return views.item_out(db, item)


# ─────────────────────────── bulk operations ───────────────────────────
@router.post("/bulk", response_model=BulkResult)
async def bulk_action(
    body: BulkRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Apply one action to many items atomically: the whole batch succeeds or
    fails together, so a half-applied state can never be left behind."""
    ids = list(dict.fromkeys(body.item_ids))  # dedupe, keep order
    items = {i.id: i for i in db.query(Item).filter(Item.id.in_(ids)).all()}
    missing = [i for i in ids if i not in items]
    if missing:
        raise HTTPException(status_code=404, detail=f"Items not found: {missing}")

    touched_card = False
    try:
        for iid in ids:
            item = items[iid]
            touched_card = touched_card or item.type == ItemType.card or bool(item.children)
            if body.action == BulkAction.move:
                if body.location_id is None:
                    raise DomainError("location_id is required for a bulk move")
                svc.move_item(db, item, body.location_id, user, body.note)
            elif body.action == BulkAction.state_change:
                if body.state is None:
                    raise DomainError("state is required for a bulk state change")
                svc.change_state(db, item, body.state, body.note, user)
            elif body.action == BulkAction.unlink:
                svc.unlink_item(db, item, user)
            elif body.action == BulkAction.link:
                if body.parent_id is None:
                    raise DomainError("parent_id is required for a bulk link")
                svc.link_item(db, item, _get(db, body.parent_id), user)
            elif body.action == BulkAction.delete:
                svc.delete_item(db, item, user)
    except Exception:
        db.rollback()
        raise

    db.commit()
    if touched_card:
        await inv_svc.check_and_alert_low_stock(db)
    return BulkResult(processed=len(ids))


# ─────────────────────── documents & extras ───────────────────────
@router.post("/{item_id}/documents", response_model=DocumentOut, status_code=201)
async def add_document(
    item_id: int,
    name: str | None = Form(None),
    doc_type: str | None = Form(None),
    url: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Attach a document: an uploaded file (multipart ``file``) or a link."""
    _get(db, item_id)
    clean_url = (url or "").strip() or None
    if file is not None and file.filename:
        doc = await files_svc.store_upload(
            db, file, user, name=name, doc_type=(doc_type or "").strip() or None,
            item_id=item_id,
        )
    elif clean_url:
        if not (name or "").strip():
            raise HTTPException(status_code=400, detail="A link needs a name")
        doc = Document(
            item_id=item_id, name=name.strip(), doc_type=(doc_type or "").strip() or None,
            url=clean_url, uploaded_by=user.id,
        )
        db.add(doc)
    else:
        raise HTTPException(status_code=400, detail="Upload a file or give a link")
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
    files_svc.delete_document(db, doc)
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
