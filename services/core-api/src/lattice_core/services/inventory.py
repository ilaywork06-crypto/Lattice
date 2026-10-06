"""Inventory & stock: per-template card stock, thresholds, low-stock alerts.

Definitions (all quantities are **sums of ``Item.quantity``**, so a commercial
card holding 25 units counts 25 and a serialised card counts 1):

* **desiccator** — a card at a location in the desiccator group
  (``Location.is_desiccator``). The desiccator is a *place*: a card assembled
  into an assembly that sits in the desiccator is in the desiccator too.
* **available** — desiccator stock in state *built* or *ok*. Cards outside the
  desiccator are presumably in use and cards that are faulty or destroyed can't
  be built with, so neither counts. This is what stock thresholds watch.
* **in use** — loose, outside the desiccator; **assembled** — inside an item
  outside the desiccator. ``assembled_in_desiccator`` breaks out the part of
  the desiccator count that sits inside assemblies.
* Destroyed cards are history, not inventory: they count nowhere.
"""

from __future__ import annotations

from collections import defaultdict

from lattice_shared.events import Event, EventType, Recipient
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from lattice_core.models import (
    AVAILABLE_STATES,
    CardType,
    ChangeRequest,
    ChangeStatus,
    Item,
    ItemState,
    ItemTemplate,
    ItemType,
    Location,
    StockThreshold,
    StorageStatus,
    User,
    UserRole,
)
from lattice_core.schemas import InventoryGroup, InventorySummary, ThresholdOut


def _live_cards(db: Session):
    return (
        db.query(Item)
        .options(joinedload(Item.location), joinedload(Item.template))
        .filter(Item.type == ItemType.card, Item.state != ItemState.destroyed)
    )


def available_quantity(db: Session, template_id: int) -> int:
    return (
        db.query(func.coalesce(func.sum(Item.quantity), 0))
        .join(Location, Item.location_id == Location.id)
        .filter(
            Item.template_id == template_id,
            Location.is_desiccator.is_(True),
            Item.state.in_(AVAILABLE_STATES),
        )
        .scalar()
        or 0
    )


# ─────────────────────────── grouped stock ───────────────────────────
def card_groups(db: Session, card_type: CardType | None = None) -> list[InventoryGroup]:
    """Stock per card template — every card template, even with no units."""
    tq = db.query(ItemTemplate).filter(ItemTemplate.type == ItemType.card)
    if card_type is not None:
        tq = tq.filter(ItemTemplate.card_type == card_type)
    templates = tq.order_by(func.lower(ItemTemplate.name)).all()
    thresholds = {t.template_id: t for t in db.query(StockThreshold).all()}

    agg: dict[int, dict] = defaultdict(lambda: {
        "total": 0, "available": 0, "desiccator": 0, "in_use": 0, "assembled": 0,
        "assembled_in_desiccator": 0, "faulty": 0, "records": 0, "serials": [],
    })
    q = _live_cards(db)
    if card_type is not None:
        q = q.join(Item.template).filter(ItemTemplate.card_type == card_type)
    for c in q.all():
        g = agg[c.template_id]
        units = c.quantity or 1
        g["records"] += 1
        g["total"] += units
        status = c.storage_status
        if status == StorageStatus.assembled:
            g["assembled"] += units
        elif status == StorageStatus.desiccator:
            g["desiccator"] += units
            if c.parent_id is not None:
                g["assembled_in_desiccator"] += units
            if c.state in AVAILABLE_STATES:
                g["available"] += units
                g["serials"].append(c.serial)
        else:
            g["in_use"] += units
        if c.state == ItemState.faulty:
            g["faulty"] += units

    out = []
    for t in templates:
        g = agg[t.id]
        threshold = thresholds.get(t.id)
        out.append(InventoryGroup(
            template_id=t.id,
            name=t.name,
            card_type=t.card_type,
            tracking=t.tracking,
            serial_prefix=t.serial_prefix,
            total=g["total"],
            available=g["available"],
            desiccator=g["desiccator"],
            in_use=g["in_use"],
            assembled=g["assembled"],
            assembled_in_desiccator=g["assembled_in_desiccator"],
            faulty=g["faulty"],
            records=g["records"],
            available_serials=sorted(g["serials"]),
            min_quantity=threshold.min_quantity if threshold else None,
            is_low=bool(threshold) and g["available"] <= threshold.min_quantity,
        ))
    return out


# ─────────────────────────── thresholds ───────────────────────────
def threshold_out(db: Session, t: StockThreshold) -> ThresholdOut:
    qty = available_quantity(db, t.template_id)
    return ThresholdOut(
        id=t.id,
        template_id=t.template_id,
        name=t.template.name,
        card_type=t.template.card_type,
        tracking=t.template.tracking,
        min_quantity=t.min_quantity,
        editor_email=t.editor_email,
        current_quantity=qty,
        is_low=qty <= t.min_quantity,
    )


def threshold_status(db: Session) -> list[ThresholdOut]:
    rows = db.query(StockThreshold).options(joinedload(StockThreshold.template)).all()
    out = [threshold_out(db, t) for t in rows]
    out.sort(key=lambda t: t.name.lower())
    return out


def low_stock(db: Session) -> list[ThresholdOut]:
    return [t for t in threshold_status(db) if t.is_low]


def _matching_managers(db: Session, t: StockThreshold) -> list[User]:
    """Managers linked to the template's cards; else every manager."""
    managers: dict[int, User] = {}
    for card in db.query(Item).filter(Item.template_id == t.template_id).all():
        for m in card.managers:
            if m.is_active:
                managers[m.id] = m
    if managers:
        return list(managers.values())
    return db.query(User).filter(User.role == UserRole.manager, User.is_active).all()


# ─────────────────────────── low-stock alert ───────────────────────────
def _component(low: ThresholdOut) -> dict:
    """One structured line of the alert — everything the UI needs to render a row."""
    return {
        "threshold_id": low.id,
        "template_id": low.template_id,
        "link": f"/cards?template={low.template_id}",
        "name": low.name,
        "card_type": low.card_type.value if low.card_type else None,
        "tracking": low.tracking.value if low.tracking else None,
        "current_quantity": low.current_quantity,
        "min_quantity": low.min_quantity,
        "shortfall": max(low.min_quantity - low.current_quantity + 1, 1),
    }


def _describe(component: dict) -> str:
    return (
        f"• {component['name']} ({component['card_type']}) — {component['current_quantity']} "
        f"available, minimum {component['min_quantity']} — {component['link']}"
    )


def _alert_body(components: list[dict]) -> str:
    """Plain-text fallback for email; the structured list travels in the payload."""
    return "\n".join([
        "The following components are at or below their minimum available stock",
        "(built or ok cards in the desiccator):",
        "",
        *(_describe(c) for c in components),
        "",
        "Open Inventory to review and restock.",
    ])


async def check_and_alert_low_stock(db: Session) -> list[ThresholdOut]:
    """Alert on every template at/under its minimum — one digest per recipient."""
    from lattice_core.events import publish_event

    lows = low_stock(db)
    if not lows:
        return []

    digests: dict[tuple, tuple[Recipient, list[dict]]] = {}

    def add(recipient: Recipient, component: dict) -> None:
        key = (recipient.user_id, recipient.email)
        digests.setdefault(key, (recipient, []))[1].append(component)

    for low in lows:
        t = db.get(StockThreshold, low.id)
        if t is None:  # deleted concurrently
            continue
        component = _component(low)
        for m in _matching_managers(db, t):
            add(Recipient(user_id=m.id, email=m.email, role="manager"), component)
        if t.editor_email:
            add(Recipient(email=t.editor_email, role="editor"), component)

    for recipient, components in digests.values():
        await publish_event(
            Event(
                type=EventType.LOW_STOCK,
                title=(
                    f"Low stock: {len(components)} component(s) below minimum"
                    if len(components) > 1
                    else f"Low stock: {components[0]['name']}"
                ),
                body=_alert_body(components),
                link=components[0]["link"] if len(components) == 1 else "/inventory",
                recipients=[recipient],
                payload={"components": components},
            )
        )
    return lows


# ─────────────────────────── dashboard summary ───────────────────────────
def summary(db: Session) -> InventorySummary:
    def units(*filters) -> int:
        return (
            db.query(func.coalesce(func.sum(Item.quantity), 0))
            .filter(Item.state != ItemState.destroyed, *filters)
            .scalar()
            or 0
        )

    # The card tiles are summed from the groups themselves, so the dashboard can
    # never disagree with the inventory table it summarises.
    groups = card_groups(db)
    return InventorySummary(
        setups=units(Item.type == ItemType.setup),
        assemblies=units(Item.type == ItemType.assembly),
        cards=sum(g.total for g in groups),
        cards_in_use=sum(g.in_use for g in groups),
        cards_desiccator=sum(g.desiccator for g in groups),
        cards_available=sum(g.available for g in groups),
        faulty_items=units(Item.state == ItemState.faulty),
        pending_change_requests=(
            db.query(func.count(ChangeRequest.id))
            .filter(ChangeRequest.status == ChangeStatus.pending)
            .scalar()
            or 0
        ),
        low_stock_alerts=len(low_stock(db)),
        templates=db.query(func.count(ItemTemplate.id)).scalar() or 0,
    )
