"""Inventory & stock: summaries, desiccator breakdown, low-stock alerts (§7, §12).

Every quantity in here is a **sum of ``Item.quantity``**, never a row count.
A serial-tracked card pins that column to 1, so summing it counts physical
boards exactly as counting rows used to; a commercial card keeps its whole
stock on one row. One formula covers both, and each group reports how it was
counted (``tracking`` + ``records``) so the number can be explained in the UI.
"""

from __future__ import annotations

from lattice_shared.events import Event, EventType, Recipient
from sqlalchemy import func
from sqlalchemy.orm import Session

from lattice_core.models import (
    CardType,
    ChangeRequest,
    ChangeStatus,
    Item,
    ItemState,
    ItemType,
    StockThreshold,
    StorageStatus,
    User,
    UserRole,
    card_tracking,
)
from lattice_core.schemas import InventoryGroup, InventorySummary, ThresholdOut


# ─────────────────────────── grouped stock ───────────────────────────
def card_groups(
    db: Session, card_type: CardType | None = None
) -> list[InventoryGroup]:
    """Stock per (card type, name, version, production date).

    Commercial cards used to be filtered out entirely, which is a large part of
    why the numbers looked arbitrary — a card could exist and be missing from
    the inventory. Every card type is reported now.
    """
    q = db.query(Item).filter(
        Item.type == ItemType.card, Item.is_template.is_(False)
    )
    if card_type is not None:
        q = q.filter(Item.card_type == card_type)

    groups: dict[tuple, dict] = {}
    for c in q.all():
        if c.card_type is None:
            continue
        key = (c.card_type, c.name, c.version, c.production_date)
        g = groups.setdefault(
            key,
            {
                "total": 0, "in_use": 0, "desiccator": 0, "assembled": 0,
                "records": 0, "serials": [],
            },
        )
        units = c.quantity or 1
        g["records"] += 1
        g["total"] += units
        if c.storage_status == StorageStatus.in_use:
            g["in_use"] += units
        elif c.storage_status == StorageStatus.desiccator:
            g["desiccator"] += units
        elif c.storage_status == StorageStatus.assembled:
            g["assembled"] += units
        if c.serial:
            g["serials"].append(c.serial)

    result = []
    for (ct, name, version, prod_date), g in groups.items():
        result.append(
            InventoryGroup(
                card_type=ct,
                tracking=card_tracking(ct),
                name=name,
                version=version,
                production_date=prod_date,
                total=g["total"],
                in_use=g["in_use"],
                desiccator=g["desiccator"],
                assembled=g["assembled"],
                # How many rows add up to `total`. For a serialised group the
                # two match (and the serials below name every unit); for a
                # commercial one a single record can carry the whole stock.
                records=g["records"],
                serials=sorted(g["serials"]),
            )
        )
    result.sort(key=lambda x: (x.card_type.value, x.name, x.version or ""))
    return result


# ─────────────────────────── thresholds ───────────────────────────
def _group_query(db: Session, t: StockThreshold):
    q = db.query(Item).filter(
        Item.type == ItemType.card,
        Item.card_type == t.card_type,
        Item.is_template.is_(False),
    )
    if t.name:
        q = q.filter(Item.name == t.name)
    if t.version:
        q = q.filter(Item.version == t.version)
    return q


def _group_quantity(db: Session, t: StockThreshold) -> int:
    """Units in the threshold's group — the sum of quantities, not the row count."""
    return (
        _group_query(db, t)
        .with_entities(func.coalesce(func.sum(Item.quantity), 0))
        .scalar()
        or 0
    )


def threshold_status(db: Session) -> list[ThresholdOut]:
    out = []
    for t in db.query(StockThreshold).all():
        qty = _group_quantity(db, t)
        out.append(
            ThresholdOut(
                id=t.id,
                card_type=t.card_type,
                tracking=card_tracking(t.card_type),
                name=t.name,
                version=t.version,
                min_quantity=t.min_quantity,
                editor_email=t.editor_email,
                current_quantity=qty,
                is_low=qty <= t.min_quantity,
            )
        )
    return out


def low_stock(db: Session) -> list[ThresholdOut]:
    return [t for t in threshold_status(db) if t.is_low]


def _matching_managers(db: Session, t: StockThreshold) -> list[User]:
    """Managers linked to any card in the threshold's group; else all managers."""
    managers: dict[int, User] = {}
    for card in _group_query(db, t).all():
        for m in card.managers:
            managers[m.id] = m
    if managers:
        return list(managers.values())
    return db.query(User).filter(User.role == UserRole.manager, User.is_active).all()


# ─────────────────────────── low-stock alert ───────────────────────────
def _component(low: ThresholdOut) -> dict:
    """One structured line of the alert — everything the UI needs to render a row."""
    return {
        "threshold_id": low.id,
        "name": low.name or "(any name)",
        "card_type": low.card_type.value,
        "tracking": low.tracking.value if low.tracking else None,
        "version": low.version,
        "current_quantity": low.current_quantity,
        "min_quantity": low.min_quantity,
        "shortfall": max(low.min_quantity - low.current_quantity + 1, 1),
    }


def _describe(component: dict) -> str:
    label = component["name"]
    if component["version"]:
        label += f" v{component['version']}"
    return (
        f"• {label} ({component['card_type']}) — {component['current_quantity']} "
        f"in stock, minimum {component['min_quantity']}"
    )


def _alert_body(components: list[dict]) -> str:
    """Plain-text fallback for email; the structured list travels in the payload."""
    return "\n".join(
        [
            "The following components are at or below their minimum stock level:",
            "",
            *(_describe(c) for c in components),
            "",
            "Open Inventory to review and restock.",
        ]
    )


async def check_and_alert_low_stock(db: Session) -> list[ThresholdOut]:
    """Alert on every group at/under its minimum — one digest per recipient.

    Previously each threshold produced its own event whose body was a sentence,
    so a manager watching four card types got four emails and had to read prose
    to find out *which* component was short. Now every recipient gets a single
    event listing exactly the components they are responsible for, as structured
    data the in-app notification renders as a table.
    """
    from lattice_core.events import publish_event

    lows = low_stock(db)
    if not lows:
        return []

    # recipient key → (recipient, their low components), preserving encounter order
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
                link="/inventory",
                recipients=[recipient],
                payload={"components": components},
            )
        )
    return lows


# ─────────────────────────── dashboard summary ───────────────────────────
def summary(db: Session) -> InventorySummary:
    def count(*filters) -> int:
        return (
            db.query(func.count(Item.id))
            .filter(Item.is_template.is_(False), *filters)
            .scalar()
            or 0
        )

    def card_units(*filters) -> int:
        """Physical cards, not card *records* — so the tiles match /inventory."""
        return (
            db.query(func.coalesce(func.sum(Item.quantity), 0))
            .filter(
                Item.is_template.is_(False), Item.type == ItemType.card, *filters
            )
            .scalar()
            or 0
        )

    return InventorySummary(
        setups=count(Item.type == ItemType.setup),
        assemblies=count(Item.type == ItemType.assembly),
        cards=card_units(),
        cards_in_use=card_units(Item.storage_status == StorageStatus.in_use),
        cards_desiccator=card_units(Item.storage_status == StorageStatus.desiccator),
        faulty_items=count(Item.state == ItemState.faulty),
        pending_change_requests=(
            db.query(func.count(ChangeRequest.id))
            .filter(ChangeRequest.status == ChangeStatus.pending)
            .scalar()
            or 0
        ),
        low_stock_alerts=len(low_stock(db)),
    )
