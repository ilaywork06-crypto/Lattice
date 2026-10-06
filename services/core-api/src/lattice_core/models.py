"""SQLAlchemy ORM models — the Lattice domain.

Design notes
------------
* **Every item is made from a template.** An ``ItemTemplate`` is the blueprint
  of one *kind* of thing — one named card, one assembly, one setup. It owns the
  name, the card type, the three-letter serial prefix and the list of
  ``TemplateField``\\ s that describe what is recorded about each unit. Items of
  one template share its name and are told apart by their serial.
* **Fields come in three modes** (see ``FieldMode``): a value fixed on the
  template and shared by every item (*white*), a list defined on the template
  that each item picks from (*white with a triangle*), or a value filled in per
  item (*grey*). A fixed value is never copied into items — it is read through
  the template — so editing it changes every item at once.
* **Values that other tables rely on live in real columns.** A field of a
  "system" type (industry/project/team, managers, responsible, location, parent,
  status, quantity) is stored as a foreign key on ``items`` (or in
  ``item_managers``), never as text, so the catalog, the inventory and the
  hierarchy can be queried with integrity. Free-form fields go to
  ``item_field_values``.
* Setups, assemblies and cards share one ``items`` table with a self-referential
  ``parent_id``; which templates may sit inside which is ``template_children``.
* "Desiccator" is a property of a *location* (``Location.is_desiccator``), not a
  status typed onto a card: a card is in the desiccator when it sits at a
  desiccator location — loose or assembled. Nothing derived is stored twice.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
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
from sqlalchemy.sql.expression import false

from lattice_core.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    """Enums are stored as checked VARCHARs, not native database enum types.

    A native PostgreSQL enum cannot drop or rename a value inside a migration
    without rebuilding every column that uses it — and this domain's
    vocabularies (states, card types) have already changed once. A named CHECK
    constraint gives the same integrity and is one statement to evolve.
    """
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )


# ─────────────────────────── Enums ───────────────────────────
class ItemType(str, enum.Enum):
    setup = "setup"        # סטאפ  — top of the tree
    assembly = "assembly"  # מכלול — sits in a setup, holds cards
    card = "card"          # כרטיס — leaf


# The letter every serial of an item type starts with (S-XXX-###, …).
SERIAL_TYPE_LETTER: dict[ItemType, str] = {
    ItemType.card: "C",
    ItemType.assembly: "A",
    ItemType.setup: "S",
}


class CardType(str, enum.Enum):
    copied = "copied"          # כרטיס מועתק (formerly "unique")
    house = "house"            # כרטיס בית   (formerly "company")
    white = "white"            # כרטיס לבן
    factory = "factory"        # כרטיס מפעל
    commercial = "commercial"  # כרטיס מסחרי


class CardTracking(str, enum.Enum):
    """How a card's stock is counted.

    A commercial card is a quantity of interchangeable parts on one row; every
    other card is one row per physical board. Both still carry a serial — it
    identifies the *record* — but only a commercial one may hold more than one
    unit.
    """

    quantity = "quantity"
    serial = "serial"


CARD_TRACKING: dict[CardType, CardTracking] = {
    CardType.copied: CardTracking.serial,
    CardType.house: CardTracking.serial,
    CardType.white: CardTracking.serial,
    CardType.factory: CardTracking.serial,
    CardType.commercial: CardTracking.quantity,
}


def card_tracking(card_type: CardType | None) -> CardTracking | None:
    """The tracking mode for a card type (``None`` for non-cards/unset)."""
    return CARD_TRACKING.get(card_type) if card_type is not None else None


class ItemState(str, enum.Enum):
    built = "built"          # בנוי — the default for every new item
    ok = "ok"                # תקין
    faulty = "faulty"        # תקול
    destroyed = "destroyed"  # הושמד


# States that count as usable stock for building (§ stock threshold).
AVAILABLE_STATES: tuple[ItemState, ...] = (ItemState.built, ItemState.ok)


class StorageStatus(str, enum.Enum):
    """Where a card physically is — *derived*, never stored (see module doc)."""

    desiccator = "desiccator"  # at a desiccator location (loose or assembled)
    assembled = "assembled"    # inside another item, outside the desiccator
    in_use = "in_use"          # loose, outside the desiccator


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
    template_create = "template_create"
    template_update = "template_update"


class CatalogCategory(str, enum.Enum):
    """Admin-managed controlled vocabularies."""

    project = "project"    # פרויקט
    industry = "industry"  # תעשייה
    team = "team"          # צוות


class FieldMode(str, enum.Enum):
    """Who decides a field's value.

    * ``fixed``  — white: set once on the template, shared by every item made
      from it and not changeable when an item is created.
    * ``choice`` — white with a list: the template defines the allowed values;
      each item picks one (the first is the default).
    * ``item``   — grey: filled in when an item is created.
    """

    fixed = "fixed"
    choice = "choice"
    item = "item"


class FieldType(str, enum.Enum):
    # free-form values (stored in item_field_values)
    text = "text"                    # טקסט חופשי
    description = "description"      # תיאור: at least N non-blank characters
    string = "string"                # מחרוזת — may carry a "XX-####" format
    serial_string = "serial_string"  # סריאלי, מחרוזת — may carry a format
    link = "link"                    # קישור
    enum = "enum"                    # רשימה של מחרוזות קבועות מראש
    letter = "letter"                # אות A–Z
    date = "date"                    # תאריך
    integer = "integer"              # מספר
    decimal = "decimal"              # מספר עשרוני
    boolean = "boolean"              # בוליאני
    files = "files"                  # צירוף קבצים (rows in `documents`)
    # system values (stored as real columns / association rows)
    industry = "industry"            # → items.industry_id
    project = "project"              # → items.project_id
    team = "team"                    # → items.team_id
    managers = "managers"            # → item_managers
    responsible = "responsible"      # → items.responsible_id
    location = "location"            # → items.location_id
    parent = "parent"                # → items.parent_id
    status = "status"                # → items.state
    quantity = "quantity"            # → items.quantity


# Field types that map onto a real column/association and therefore may appear
# at most once per template.
SYSTEM_FIELD_TYPES: frozenset[FieldType] = frozenset({
    FieldType.industry, FieldType.project, FieldType.team, FieldType.managers,
    FieldType.responsible, FieldType.location, FieldType.parent, FieldType.status,
    FieldType.quantity,
})

# Physical, per-unit state: it makes no sense to fix it for every unit at once,
# so these can be a per-item value or a list with a default, never `fixed`.
PER_UNIT_FIELD_TYPES: frozenset[FieldType] = frozenset({
    FieldType.location, FieldType.parent, FieldType.status, FieldType.quantity,
})

CATALOG_FIELD_TYPES: dict[FieldType, CatalogCategory] = {
    FieldType.industry: CatalogCategory.industry,
    FieldType.project: CatalogCategory.project,
    FieldType.team: CatalogCategory.team,
}


# ─────────────────── Association tables ───────────────────
# Which managers "own" an item (targeted approval routing + manager log).
item_managers = Table(
    "item_managers",
    Base.metadata,
    Column("item_id", ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

# Which templates may be placed inside which (assembly → cards, setup →
# assemblies/cards). A pair appears at most once; a child template may belong to
# any number of parents.
template_children = Table(
    "template_children",
    Base.metadata,
    Column(
        "parent_template_id",
        ForeignKey("item_templates.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "child_template_id",
        ForeignKey("item_templates.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
    # How many units of the child template one parent item may hold: at least
    # ``min_count`` for the parent to be complete, never more than ``max_count``
    # (NULL = no upper limit).
    Column("min_count", Integer, nullable=False, server_default="0"),
    Column("max_count", Integer, nullable=True),
    CheckConstraint("parent_template_id <> child_template_id", name="not_self"),
    CheckConstraint("min_count >= 0", name="min_count_non_negative"),
    CheckConstraint(
        "max_count IS NULL OR (max_count >= 1 AND max_count >= min_count)",
        name="max_count_valid",
    ),
)


# ─────────────────────────── Users ───────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(_enum(UserRole, "user_role"), default=UserRole.viewer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Sign-in screen shortcuts (§8). A manager decides which accounts are offered
    # there and whether the password is pre-filled too. The endpoint serving
    # these is necessarily unauthenticated — it *is* the login page — so both
    # default to off and nothing is published without a deliberate decision.
    login_hint_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    login_hint_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    managed_items: Mapped[list[Item]] = relationship(
        secondary=item_managers, back_populates="managers"
    )

    @property
    def has_login_hint_password(self) -> bool:
        """Whether a password is published with this account's shortcut.

        The value itself is never handed back through the authenticated API —
        managers set a new one rather than reading the old one back.
        """
        return bool(self.login_hint_password)


# ───────────────────────── Locations ─────────────────────────
class Location(Base):
    """Physical location — also carries x/y for the floor-plan map."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    building: Mapped[str | None] = mapped_column(String(255), nullable=True)
    room: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Normalised 0..100 coordinates on the floor-plan map.
    x: Mapped[float] = mapped_column(default=50.0)
    y: Mapped[float] = mapped_column(default=50.0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Part of the desiccator group: loose cards here are stock available for
    # building; anywhere else they are in use.
    is_desiccator: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), index=True
    )

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


# ─────────────────────────── Catalog ───────────────────────────
class CatalogOption(Base):
    """An admin-defined allowed value for projects / industries / teams.

    Items reference these by id, so a rename is one row and a value that is in
    use cannot be deleted from under the items holding it.
    """

    __tablename__ = "catalog_options"
    __table_args__ = (
        UniqueConstraint("category", "value", name="uq_catalog_category_value"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[CatalogCategory] = mapped_column(
        _enum(CatalogCategory, "catalog_category"), index=True
    )
    value: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CatalogLink(Base):
    """A two-way link between two catalog values of different categories.

    Team ↔ industry, team ↔ project, industry ↔ project — each many-to-many. A
    link has no direction, so it is stored **once**, with the smaller id first
    (``option_a_id < option_b_id``); reading "the projects of team T" and "the
    teams of project P" are the same lookup from either end, and the pair
    cannot be recorded twice in opposite orders.
    """

    __tablename__ = "catalog_links"
    __table_args__ = (
        CheckConstraint("option_a_id < option_b_id", name="ordered_pair"),
    )

    option_a_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_options.id", ondelete="CASCADE"), primary_key=True
    )
    option_b_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_options.id", ondelete="CASCADE"), primary_key=True, index=True
    )


# ─────────────────────────── Templates ───────────────────────────
class ItemTemplate(Base):
    """The blueprint every item is created from (one per named card/assembly/setup)."""

    __tablename__ = "item_templates"
    __table_args__ = (
        UniqueConstraint("type", "name", name="uq_item_templates_type_name"),
        UniqueConstraint("type", "serial_prefix", name="uq_item_templates_type_prefix"),
        # Card templates carry a card type; nothing else does.
        CheckConstraint(
            "(type = 'card' AND card_type IS NOT NULL) OR "
            "(type <> 'card' AND card_type IS NULL)",
            name="card_type_only_on_cards",
        ),
        CheckConstraint("length(serial_prefix) = 3", name="serial_prefix_len"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[ItemType] = mapped_column(_enum(ItemType, "item_type"), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    card_type: Mapped[CardType | None] = mapped_column(
        _enum(CardType, "card_type"), nullable=True, index=True
    )
    # The XXX in C-XXX-### — three upper-case Latin letters.
    serial_prefix: Mapped[str] = mapped_column(String(3))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    fields: Mapped[list[TemplateField]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateField.position",
    )
    # The editable side: one row per allowed child template, with its limits.
    child_links: Mapped[list[TemplateChild]] = relationship(
        foreign_keys=lambda: [TemplateChild.parent_template_id],
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    # Read-only conveniences over the same rows.
    child_templates: Mapped[list[ItemTemplate]] = relationship(
        secondary=template_children,
        primaryjoin=lambda: ItemTemplate.id == template_children.c.parent_template_id,
        secondaryjoin=lambda: ItemTemplate.id == template_children.c.child_template_id,
        viewonly=True,
    )
    parent_templates: Mapped[list[ItemTemplate]] = relationship(
        secondary=template_children,
        primaryjoin=lambda: ItemTemplate.id == template_children.c.child_template_id,
        secondaryjoin=lambda: ItemTemplate.id == template_children.c.parent_template_id,
        viewonly=True,
    )
    items: Mapped[list[Item]] = relationship(back_populates="template")

    @property
    def tracking(self) -> CardTracking | None:
        return card_tracking(self.card_type)


class TemplateField(Base):
    """One field of a template: its name, its type and who fills it in."""

    __tablename__ = "template_fields"
    __table_args__ = (
        UniqueConstraint("template_id", "key", name="uq_template_fields_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("item_templates.id", ondelete="CASCADE"), index=True
    )
    # Stable machine name, unique within the template (used by the API/import).
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(255))
    field_type: Mapped[FieldType] = mapped_column(_enum(FieldType, "field_type"))
    mode: Mapped[FieldMode] = mapped_column(_enum(FieldMode, "field_mode"))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Per-type settings: `options` (the list of a `choice` field / an enum's
    # values), `pattern` ("XX-#####"), `min_length` (description).
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    # The shared value of a `fixed` field (ids for reference types).
    fixed_value: Mapped[object | None] = mapped_column(JSON, nullable=True)

    template: Mapped[ItemTemplate] = relationship(back_populates="fields")


class TemplateChild(Base):
    """One entry of a template's contents: which template may sit inside it and
    how many units of it one item holds (``min_count`` .. ``max_count``)."""

    __table__ = template_children

    parent: Mapped[ItemTemplate] = relationship(
        foreign_keys=[template_children.c.parent_template_id],
        back_populates="child_links",
    )
    child: Mapped[ItemTemplate] = relationship(
        foreign_keys=[template_children.c.child_template_id],
    )


class FieldGroup(Base):
    """A named, reusable set of field definitions kept in the catalog.

    Loading a group into the template editor copies its fields into the new
    template; the template does not stay linked to the group, so editing a group
    later never changes existing templates (or their items) behind anyone's back.
    """

    __tablename__ = "field_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    fields: Mapped[list[FieldGroupField]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="FieldGroupField.position",
    )


class FieldGroupField(Base):
    """One field definition of a field group (the same shape as a TemplateField)."""

    __tablename__ = "field_group_fields"
    __table_args__ = (
        UniqueConstraint("group_id", "key", name="uq_field_group_fields_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("field_groups.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(255))
    field_type: Mapped[FieldType] = mapped_column(_enum(FieldType, "field_type"))
    mode: Mapped[FieldMode] = mapped_column(_enum(FieldMode, "field_mode"))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    fixed_value: Mapped[object | None] = mapped_column(JSON, nullable=True)

    group: Mapped[FieldGroup] = relationship(back_populates="fields")


# ─────────────────────────── Items ───────────────────────────
class Item(Base):
    __tablename__ = "items"
    __table_args__ = (CheckConstraint("quantity >= 1", name="quantity_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # RESTRICT: a template with items cannot vanish from under them.
    template_id: Mapped[int] = mapped_column(
        ForeignKey("item_templates.id", ondelete="RESTRICT"), index=True
    )
    # Mirrors template.type, which never changes after a template is created;
    # kept on the row because every hierarchy rule and list filters on it.
    type: Mapped[ItemType] = mapped_column(_enum(ItemType, "item_type"), index=True)
    # S-XXX-### / A-XXX-### / C-XXX-### — unique across the whole system.
    serial: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    state: Mapped[ItemState] = mapped_column(
        _enum(ItemState, "item_state"), default=ItemState.built, index=True
    )

    # Hierarchy (self-referential) and physical location
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Units this row stands for: > 1 only for commercial cards.
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # System fields (see FieldType) — real foreign keys, never free text.
    industry_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_options.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_options.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_options.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    responsible_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    template: Mapped[ItemTemplate] = relationship(back_populates="items")
    parent: Mapped[Item | None] = relationship(
        remote_side="Item.id", back_populates="children"
    )
    children: Mapped[list[Item]] = relationship(
        back_populates="parent", cascade="save-update", order_by="Item.serial"
    )
    location: Mapped[Location | None] = relationship(back_populates="items")
    industry: Mapped[CatalogOption | None] = relationship(foreign_keys=[industry_id])
    project: Mapped[CatalogOption | None] = relationship(foreign_keys=[project_id])
    team: Mapped[CatalogOption | None] = relationship(foreign_keys=[team_id])
    responsible: Mapped[User | None] = relationship(foreign_keys=[responsible_id])
    managers: Mapped[list[User]] = relationship(
        secondary=item_managers, back_populates="managed_items"
    )
    field_values: Mapped[list[ItemFieldValue]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    state_history: Mapped[list[StateHistory]] = relationship(
        back_populates="item", cascade="all, delete-orphan", order_by="StateHistory.changed_at"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        foreign_keys="Document.item_id",
        order_by="Document.created_at",
    )
    extra_items: Mapped[list[ExtraItem]] = relationship(
        back_populates="setup", cascade="all, delete-orphan"
    )

    @property
    def name(self) -> str:
        """An item is named by its template; its serial tells it apart."""
        return self.template.name if self.template is not None else ""

    @property
    def card_type(self) -> CardType | None:
        return self.template.card_type if self.template is not None else None

    @property
    def label(self) -> str:
        return f"{self.name} ({self.serial})"

    @property
    def storage_status(self) -> StorageStatus | None:
        """Where a card is, derived from its parent and its location."""
        if self.type != ItemType.card:
            return None
        # The desiccator is a place: a card at a desiccator location is in it,
        # whether loose or assembled into something that sits there.
        if self.location is not None and self.location.is_desiccator:
            return StorageStatus.desiccator
        if self.parent_id is not None:
            return StorageStatus.assembled
        return StorageStatus.in_use


class ItemFieldValue(Base):
    """The value of a free-form (non-system) template field on one item."""

    __tablename__ = "item_field_values"
    __table_args__ = (
        UniqueConstraint("item_id", "field_id", name="uq_item_field_values_item_field"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    field_id: Mapped[int] = mapped_column(
        ForeignKey("template_fields.id", ondelete="CASCADE"), index=True
    )
    value: Mapped[object | None] = mapped_column(JSON, nullable=True)

    item: Mapped[Item] = relationship(back_populates="field_values")
    field: Mapped[TemplateField] = relationship()


class StateHistory(Base):
    """Append-only log of state transitions (with mandatory note for faults)."""

    __tablename__ = "state_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    state: Mapped[ItemState] = mapped_column(_enum(ItemState, "item_state"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    item: Mapped[Item] = relationship(back_populates="state_history")
    user: Mapped[User | None] = relationship()

    @property
    def changed_by_name(self) -> str | None:
        return self.user.full_name if self.user is not None else None


class Document(Base):
    """A document attached to an item or template: an uploaded file or a link.

    An upload is stored on disk under ``storage_key`` (see services/files.py)
    and served back through the API, so it is protected by the same sign-in as
    everything else. ``field_id`` ties it to a *files* template field; without
    one it is a general document of the item.

    A file can be uploaded *before* the item it belongs to exists (a form with a
    files field, or a proposal waiting for approval): it is then **staged** —
    no item and no template yet — and is attached when the item is created.
    Stale staged uploads are swept away (services/files.py).
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("url IS NOT NULL OR storage_key IS NOT NULL", name="has_content"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("item_templates.id", ondelete="CASCADE"), nullable=True, index=True
    )
    field_id: Mapped[int | None] = mapped_column(
        ForeignKey("template_fields.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    item: Mapped[Item | None] = relationship(back_populates="documents", foreign_keys=[item_id])

    @property
    def is_file(self) -> bool:
        return self.storage_key is not None


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
    action: Mapped[ChangeAction] = mapped_column(_enum(ChangeAction, "change_action"))
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("item_templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_type: Mapped[ItemType | None] = mapped_column(
        _enum(ItemType, "item_type"), nullable=True
    )
    item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The structured mutation to apply on approval.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text)  # מה השינוי
    reason: Mapped[str] = mapped_column(Text)       # למה השינוי

    status: Mapped[ChangeStatus] = mapped_column(
        _enum(ChangeStatus, "change_status"), default=ChangeStatus.pending, index=True
    )
    # RESTRICT: a proposal keeps its author for the audit trail.
    proposed_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    proposer: Mapped[User] = relationship(foreign_keys=[proposed_by])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])


class AuditLog(Base):
    """Immutable change log (requirement §10)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("item_templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Snapshot of what the row was called at the time — survives a deletion.
    item_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class StockThreshold(Base):
    """Minimum available stock for one card template.

    "Available" means units that can be built with right now: loose cards at a
    desiccator location whose state is built or ok (see services/inventory.py).
    """

    __tablename__ = "stock_thresholds"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("item_templates.id", ondelete="CASCADE"), unique=True, index=True
    )
    min_quantity: Mapped[int] = mapped_column(Integer, default=0)
    # Extra recipient (besides the template's managers) for the low-stock alert.
    editor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    template: Mapped[ItemTemplate] = relationship()
