"""SQLAlchemy ORM models — the Lattice domain.

Design notes
------------
* Setups, assemblies and cards are all rows in a single ``items`` table with a
  ``type`` discriminator. This keeps the *hierarchy* uniform: every item can be
  a child of another via ``parent_id`` (self-referential), so a card can sit in
  an assembly which sits in a setup, and we can walk the tree either way.
* "Linking item" (פריט מקשר) = an item that has children.
  "Linked item" (פריט מקושר) = an item that has a parent.
* Moving a linking item cascades location to its descendants; moving a linked
  item never touches its parent (see services/items.py).
"""

from __future__ import annotations

import enum
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lattice_core.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ─────────────────────────── Enums ───────────────────────────
class ItemType(str, enum.Enum):
    setup = "setup"        # סטאפ  — linking item (top of the tree)
    assembly = "assembly"  # מכלול — linking *or* linked
    card = "card"          # כרטיס — linked item (leaf)


class CardType(str, enum.Enum):
    commercial = "commercial"  # כרטיס מסחרי
    company = "company"        # כרטיס מדור / חברה
    unique = "unique"          # כרטיס ייחודי


class ItemState(str, enum.Enum):
    production = "production"  # ייצור
    built = "built"            # בנוי
    used = "used"              # מושמש
    working = "working"        # עובד
    faulty = "faulty"          # תקול


class StorageStatus(str, enum.Enum):
    assembled = "assembled"    # מורכב בתוך פריט אחר
    in_use = "in_use"          # בשימוש (עצמאי)
    desiccator = "desiccator"  # מאוחסן בדסיקטור


class UserRole(str, enum.Enum):
    viewer = "viewer"    # צופה
    editor = "editor"    # עורך
    manager = "manager"  # מנהל


class ChangeStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ChangeAction(str, enum.Enum):
    create = "create"
    update = "update"
    delete = "delete"
    move = "move"
    link = "link"
    unlink = "unlink"
    state_change = "state_change"


class CatalogCategory(str, enum.Enum):
    """Admin-managed controlled vocabularies (requirement §2)."""

    project = "project"    # שם פרויקט
    industry = "industry"  # תעשייה


# ─────────────────── Association tables ───────────────────
# Which managers "own" an item (targeted approval routing + manager log).
item_managers = Table(
    "item_managers",
    Base.metadata,
    Column("item_id", ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


# ─────────────────────────── Users ───────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.viewer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    managed_items: Mapped[list[Item]] = relationship(
        secondary=item_managers, back_populates="managers"
    )


# ───────────────────────── Locations ─────────────────────────
class Location(Base):
    """Physical location — also carries x/y for the map POC."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    building: Mapped[str | None] = mapped_column(String(255), nullable=True)
    room: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Normalised 0..100 coordinates on the floor-plan POC map.
    x: Mapped[float] = mapped_column(default=50.0)
    y: Mapped[float] = mapped_column(default=50.0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list[Item]] = relationship(back_populates="location")


class MapBuilding(Base):
    """An editable building/zone drawn on the floor-plan background.

    All coordinates are normalised 0..100 (x/y = top-left corner) to match the
    location markers, so the whole map stays resolution-independent.
    """

    __tablename__ = "map_buildings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    x: Mapped[float] = mapped_column(default=5.0)
    y: Mapped[float] = mapped_column(default=5.0)
    width: Mapped[float] = mapped_column(default=30.0)
    height: Mapped[float] = mapped_column(default=20.0)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ─────────────────────────── Items ───────────────────────────
class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[ItemType] = mapped_column(Enum(ItemType), index=True)

    # A template is a reusable blueprint used to spin up new items quickly. It
    # never takes part in the live hierarchy, inventory or the map (§5).
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Common documentation
    name: Mapped[str] = mapped_column(String(255), index=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)  # תעשייה
    project: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    team: Mapped[str | None] = mapped_column(String(255), nullable=True)  # צוות/מי בנה
    state: Mapped[ItemState] = mapped_column(Enum(ItemState), default=ItemState.production)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)  # תיאור מילולי
    dmz: Mapped[str | None] = mapped_column(Text, nullable=True)  # דמ"צ מפורט

    # Hierarchy (self-referential)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── Card-specific (nullable for setups/assemblies) ──
    card_type: Mapped[CardType | None] = mapped_column(Enum(CardType), nullable=True, index=True)
    responsible: Mapped[str | None] = mapped_column(String(255), nullable=True)  # אחראי כרטיס
    lead: Mapped[str | None] = mapped_column(String(255), nullable=True)  # מוביל אחראי
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    storage_status: Mapped[StorageStatus | None] = mapped_column(
        Enum(StorageStatus), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    parent: Mapped[Item | None] = relationship(
        remote_side="Item.id", back_populates="children"
    )
    children: Mapped[list[Item]] = relationship(
        back_populates="parent", cascade="save-update"
    )
    location: Mapped[Location | None] = relationship(back_populates="items")
    managers: Mapped[list[User]] = relationship(
        secondary=item_managers, back_populates="managed_items"
    )
    state_history: Mapped[list[StateHistory]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="StateHistory.changed_at"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    extra_items: Mapped[list[ExtraItem]] = relationship(
        back_populates="setup", cascade="all, delete-orphan"
    )


class StateHistory(Base):
    """Append-only log of state transitions (with mandatory note for faults)."""

    __tablename__ = "state_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    state: Mapped[ItemState] = mapped_column(Enum(ItemState))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    item: Mapped[Item] = relationship(back_populates="state_history")


class Document(Base):
    """Relevant documents for a card (research, test files, …)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    item: Mapped[Item] = relationship(back_populates="documents")


class ExtraItem(Base):
    """Non-card accessories living inside a setup (power supplies, burners, …)."""

    __tablename__ = "extra_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    setup_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    company_part_number: Mapped[str | None] = mapped_column(String(128), nullable=True)  # מק"ט
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    signed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)  # מי חתום

    setup: Mapped[Item] = relationship(back_populates="extra_items")


class ChangeRequest(Base):
    """A proposed mutation awaiting manager approval (requirement §9)."""

    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[ChangeAction] = mapped_column(Enum(ChangeAction))
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_type: Mapped[ItemType | None] = mapped_column(Enum(ItemType), nullable=True)
    item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The structured mutation to apply on approval.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text)  # מה השינוי
    reason: Mapped[str] = mapped_column(Text)       # למה השינוי

    status: Mapped[ChangeStatus] = mapped_column(
        Enum(ChangeStatus), default=ChangeStatus.pending, index=True
    )
    proposed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    proposer: Mapped[User] = relationship(foreign_keys=[proposed_by])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])


class AuditLog(Base):
    """Immutable per-item change log (requirement §10)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class CatalogOption(Base):
    """An admin-defined allowed value for projects / industries (requirement §2).

    Items may only reference values that exist here (and are active), so the
    vocabulary stays clean as the system scales to many users.
    """

    __tablename__ = "catalog_options"
    __table_args__ = (
        UniqueConstraint("category", "value", name="uq_catalog_category_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[CatalogCategory] = mapped_column(Enum(CatalogCategory), index=True)
    value: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class StockThreshold(Base):
    """Minimum-quantity alerting per card group (requirement §12)."""

    __tablename__ = "stock_thresholds"

    id: Mapped[int] = mapped_column(primary_key=True)
    card_type: Mapped[CardType] = mapped_column(Enum(CardType))
    # Optional narrowing of the group the threshold applies to.
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    min_quantity: Mapped[int] = mapped_column(Integer, default=0)
    # Extra recipients (besides linked managers) for the low-stock alert.
    editor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
