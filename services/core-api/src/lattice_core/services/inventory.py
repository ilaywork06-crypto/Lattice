"""Inventory & stock: summaries, desiccator breakdown, low-stock alerts (§7, §12)."""

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
)
from lattice_core.schemas import InventoryGroup, InventorySummary, ThresholdOut

TRACKED_CARD_TYPES = (CardType.company, CardType.unique)


# ─────────────────────────── grouped stock ───────────────────────────
def card_groups(
    db: Session, card_type: CardType | None = None
) -> list[InventoryGroup]:
    q = db.query(Item).filter(
        Item.type == ItemType.card, Item.is_template.is_(False)
    )
    if card_type is not None:
        q = q.filter(Item.card_type == card_type)
    else:
        q = q.filter(Item.card_type.in_(TRACKED_CARD_TYPES))

    groups: dict[tuple, dict] = {}
    for c in q.all():
        key = (c.card_type, c.name, c.version, c.production_date)
        g = groups.setdefault(
            key,
            {"total": 0, "in_use": 0, "desiccator": 0, "assembled": 0, "serials": []},
        )
        g["total"] += 1
        if c.storage_status == StorageStatus.in_use:
            g["in_use"] += 1
        elif c.storage_status == StorageStatus.desiccator:
            g["desiccator"] += 1
        elif c.storage_status == StorageStatus.assembled:
            g["assembled"] += 1
        if c.serial:
            g["serials"].append(c.serial)

    result = []
    for (ct, name, version, prod_date), g in groups.items():
        result.append(
            InventoryGroup(
                card_type=ct,
                name=name,
                version=version,
                production_date=prod_date,
                total=g["total"],
                in_use=g["in_use"],
                desiccator=g["desiccator"],
                assembled=g["assembled"],
                # unique cards are tracked per-serial (§12); company cards are not.
                serials=sorted(g["serials"]) if ct == CardType.unique else [],
            )
        )
    result.sort(key=lambda x: (x.card_type.value, x.name, x.version or ""))
    return result


# ─────────────────────────── thresholds ───────────────────────────
def _group_quantity(db: Session, t: StockThreshold) -> int:
    q = db.query(func.count(Item.id)).filter(
        Item.type == ItemType.card,
        Item.card_type == t.card_type,
        Item.is_template.is_(False),
    )
    if t.name:
        q = q.filter(Item.name == t.name)
    if t.version:
        q = q.filter(Item.version == t.version)
    return q.scalar() or 0


def threshold_status(db: Session) -> list[ThresholdOut]:
    out = []
    for t in db.query(StockThreshold).all():
        qty = _group_quantity(db, t)
        out.append(
            ThresholdOut(
                id=t.id,
                card_type=t.card_type,
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
    q = db.query(Item).filter(
        Item.type == ItemType.card,
        Item.card_type == t.card_type,
        Item.is_template.is_(False),
    )
    if t.name:
        q = q.filter(Item.name == t.name)
    if t.version:
        q = q.filter(Item.version == t.version)
    managers: dict[int, User] = {}
    for card in q.all():
        for m in card.managers:
            managers[m.id] = m
    if managers:
        return list(managers.values())
    return db.query(User).filter(User.role == UserRole.manager, User.is_active).all()


async def check_and_alert_low_stock(db: Session) -> list[ThresholdOut]:
    """Publish a low-stock event for every group at/under its minimum."""
    from lattice_core.events import publish_event

    lows = low_stock(db)
    for low in lows:
        t = db.get(StockThreshold, low.id)
        recipients = [
            Recipient(user_id=m.id, email=m.email, role="manager")
            for m in _matching_managers(db, t)
        ]
        if t.editor_email:
            recipients.append(Recipient(email=t.editor_email, role="editor"))
        label = f"{t.card_type.value} card '{t.name or 'any'}'"
        if t.version:
            label += f" v{t.version}"
        await publish_event(
            Event(
                type=EventType.LOW_STOCK,
                title="Low stock alert",
                body=(
                    f"{label} has {low.current_quantity} unit(s) — at or below the "
                    f"minimum of {t.min_quantity}. Consider producing/ordering more."
                ),
                link="/inventory",
                recipients=recipients,
                payload={
                    "threshold_id": t.id,
                    "current_quantity": low.current_quantity,
                    "min_quantity": t.min_quantity,
                },
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

    return InventorySummary(
        setups=count(Item.type == ItemType.setup),
        assemblies=count(Item.type == ItemType.assembly),
        cards=count(Item.type == ItemType.card),
        cards_in_use=count(
            Item.type == ItemType.card, Item.storage_status == StorageStatus.in_use
        ),
        cards_desiccator=count(
            Item.type == ItemType.card, Item.storage_status == StorageStatus.desiccator
        ),
        faulty_items=count(Item.state == ItemState.faulty),
        pending_change_requests=(
            db.query(func.count(ChangeRequest.id))
            .filter(ChangeRequest.status == ChangeStatus.pending)
            .scalar()
            or 0
        ),
        low_stock_alerts=len(low_stock(db)),
    )
