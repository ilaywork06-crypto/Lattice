"""Pydantic (v2) request/response schemas."""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from lattice_core.models import (
    CardTracking,
    CardType,
    CatalogCategory,
    ChangeAction,
    ChangeStatus,
    ItemState,
    ItemType,
    StorageStatus,
    UserRole,
)

BCRYPT_MAX_BYTES = 72


def _within_bcrypt_limit(value: str) -> str:
    """bcrypt refuses anything over 72 *bytes* and raises, which surfaced as a 500.

    Bytes, not characters: UTF-8 makes Hebrew two bytes apiece, so a 40-character
    passphrase can already be over the line. Checked here so the caller gets a
    422 that explains itself.
    """
    encoded = len(value.encode("utf-8"))
    if encoded > BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password is too long for bcrypt: {encoded} bytes, maximum is "
            f"{BCRYPT_MAX_BYTES} (non-Latin characters use 2–4 bytes each)."
        )
    return value


Password = Annotated[str, Field(min_length=6), AfterValidator(_within_bcrypt_limit)]


# ─────────────────────────── Auth / users ───────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    full_name: str
    user_id: int


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: EmailStr
    role: UserRole


class UserOut(UserBrief):
    is_active: bool
    created_at: datetime
    login_hint_visible: bool = False
    # Whether a password is published alongside the shortcut — never the value.
    has_login_hint_password: bool = False


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: Password
    role: UserRole = UserRole.viewer


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: Password | None = None
    # Offer this account on the sign-in screen (see LoginHintOut).
    login_hint_visible: bool | None = None
    # Password to pre-fill with the shortcut. `""` clears it, leaving an account
    # whose email is filled in but whose password still has to be typed.
    login_hint_password: str | None = None


class LoginHintOut(BaseModel):
    """A sign-in shortcut, served **unauthenticated** to the login page.

    Only accounts a manager marked visible appear here, and `password` is filled
    in only where a manager explicitly published one.
    """

    full_name: str
    email: EmailStr
    role: UserRole
    password: str | None = None


# ─────────────────────────── Locations ───────────────────────────
class LocationCreate(BaseModel):
    name: str
    building: str | None = None
    room: str | None = None
    x: float = 50.0
    y: float = 50.0
    notes: str | None = None


class LocationOut(LocationCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_count: int = 0


# ─────────────────────────── Map buildings ───────────────────────────
class MapBuildingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    x: float = 5.0
    y: float = 5.0
    width: float = Field(default=30.0, gt=0)
    height: float = Field(default=20.0, gt=0)
    color: str | None = None
    notes: str | None = None
    sort_order: int = 0


class MapBuildingUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    x: float | None = None
    y: float | None = None
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    color: str | None = None
    notes: str | None = None
    sort_order: int | None = None


class MapBuildingOut(MapBuildingCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ─────────────────────────── Catalog (admin vocabularies) ───────────────────────────
class CatalogOptionCreate(BaseModel):
    category: CatalogCategory
    value: str = Field(min_length=1, max_length=255)
    description: str | None = None
    active: bool = True
    sort_order: int = 0


class CatalogOptionUpdate(BaseModel):
    value: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    active: bool | None = None
    sort_order: int | None = None


class CatalogOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category: CatalogCategory
    value: str
    description: str | None
    active: bool
    sort_order: int
    usage_count: int = 0


# ─────────────────────────── Nested item bits ───────────────────────────
class StateHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    state: ItemState
    note: str | None
    changed_by: int | None
    changed_at: datetime


class DocumentCreate(BaseModel):
    name: str
    url: str | None = None
    doc_type: str | None = None


class DocumentOut(DocumentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ExtraItemCreate(BaseModel):
    name: str
    company_part_number: str | None = None
    serial: str | None = None
    signed_by: str | None = None


class ExtraItemOut(ExtraItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ─────────────────────────── Items ───────────────────────────
class ItemBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: ItemType
    name: str
    state: ItemState
    card_type: CardType | None = None
    serial: str | None = None
    version: str | None = None
    location_id: int | None = None


class ItemListOut(BaseModel):
    """Compact representation for list/table views."""

    id: int
    type: ItemType
    name: str
    industry: str | None = None
    project: str | None = None
    team: str | None = None
    state: ItemState
    card_type: CardType | None = None
    version: str | None = None
    serial: str | None = None
    quantity: int = 1
    storage_status: StorageStatus | None = None
    parent_id: int | None = None
    location_id: int | None = None
    location_name: str | None = None
    children_count: int = 0
    is_template: bool = False
    manager_names: list[str] = Field(default_factory=list)
    updated_at: datetime


class ItemCreate(BaseModel):
    type: ItemType
    name: str
    industry: str | None = None
    project: str | None = None
    team: str | None = None
    state: ItemState = ItemState.production
    description: str | None = None
    dmz: str | None = None
    location_id: int | None = None
    parent_id: int | None = None
    is_template: bool = False
    # card-specific
    card_type: CardType | None = None
    responsible: str | None = None
    lead: str | None = None
    production_date: date | None = None
    version: str | None = None
    serial: str | None = None
    # Commercial cards only: how many interchangeable units this row holds.
    # Serial-tracked cards are one row per unit and must leave it at 1.
    quantity: int = Field(default=1, ge=1)
    storage_status: StorageStatus | None = None
    # linked manager ids
    manager_ids: list[int] = Field(default_factory=list)
    # existing items to pull in as children on creation (bidirectional linking, §6/§8):
    # a setup can adopt assemblies *and* cards, an assembly can adopt cards.
    child_ids: list[int] = Field(default_factory=list)


class ItemUpdate(BaseModel):
    name: str | None = None
    industry: str | None = None
    project: str | None = None
    team: str | None = None
    description: str | None = None
    dmz: str | None = None
    card_type: CardType | None = None
    responsible: str | None = None
    lead: str | None = None
    production_date: date | None = None
    version: str | None = None
    serial: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    storage_status: StorageStatus | None = None
    location_id: int | None = None
    state: ItemState | None = None
    # Carries the explanation the faulty-transition rule demands, so the edit
    # form can change state without a second round-trip through StateDialog.
    state_note: str | None = None
    manager_ids: list[int] | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: ItemType
    is_template: bool = False
    name: str
    industry: str | None
    project: str | None
    team: str | None
    state: ItemState
    description: str | None
    dmz: str | None
    parent_id: int | None
    location_id: int | None
    card_type: CardType | None
    responsible: str | None
    lead: str | None
    production_date: date | None
    version: str | None
    serial: str | None
    quantity: int = 1
    storage_status: StorageStatus | None
    created_at: datetime
    updated_at: datetime
    location: LocationOut | None = None
    parent: ItemBrief | None = None
    children: list[ItemBrief] = Field(default_factory=list)
    managers: list[UserBrief] = Field(default_factory=list)
    state_history: list[StateHistoryOut] = Field(default_factory=list)
    documents: list[DocumentOut] = Field(default_factory=list)
    extra_items: list[ExtraItemOut] = Field(default_factory=list)


class MoveRequest(BaseModel):
    location_id: int
    note: str | None = None


class LinkRequest(BaseModel):
    parent_id: int


class ChildrenRequest(BaseModel):
    """The container's contents *after* the edit — not a delta."""

    child_ids: list[int] = Field(default_factory=list)


class StateChangeRequest(BaseModel):
    state: ItemState
    note: str | None = None


# ─────────────────────────── Change requests ───────────────────────────
class ChangeRequestCreate(BaseModel):
    action: ChangeAction
    item_id: int | None = None
    item_type: ItemType | None = None
    payload: dict = Field(default_factory=dict)
    description: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ChangeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: ChangeAction
    item_id: int | None
    item_type: ItemType | None
    item_name: str | None
    payload: dict
    description: str
    reason: str
    status: ChangeStatus
    proposed_by: int
    reviewed_by: int | None
    review_note: str | None
    created_at: datetime
    reviewed_at: datetime | None
    proposer: UserBrief | None = None
    reviewer: UserBrief | None = None


class ReviewRequest(BaseModel):
    note: str | None = None


# ─────────────────────────── Audit ───────────────────────────
class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int | None
    item_name: str | None
    action: str
    summary: str
    details: dict
    user_id: int | None
    user_name: str | None
    created_at: datetime


# ─────────────────────────── Inventory ───────────────────────────
class ThresholdCreate(BaseModel):
    """Created from a card that exists, not from a typed-in name.

    The server derives the watched group (`card_type`, `name`, `version`) from
    `item_id`, so a threshold can never point at a model nobody stocks.
    """

    item_id: int
    min_quantity: int = Field(default=0, ge=0)
    editor_email: EmailStr | None = None
    # Watch every version of the chosen card's model instead of just its own.
    any_version: bool = False


class ThresholdOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    item_id: int | None = None
    card_type: CardType
    name: str | None = None
    version: str | None = None
    min_quantity: int = 0
    editor_email: EmailStr | None = None
    tracking: CardTracking | None = None
    current_quantity: int = 0
    is_low: bool = False


class InventoryGroup(BaseModel):
    card_type: CardType
    # How `total` was arrived at: summed quantities on one (or few) commercial
    # records, or one row per serialised unit. The UI shows this so nobody has
    # to guess where the number came from.
    tracking: CardTracking | None = None
    name: str
    version: str | None = None
    production_date: date | None = None
    total: int
    in_use: int
    desiccator: int
    assembled: int
    records: int = 0
    serials: list[str] = Field(default_factory=list)


class InventorySummary(BaseModel):
    setups: int
    assemblies: int
    cards: int
    cards_in_use: int
    cards_desiccator: int
    faulty_items: int
    pending_change_requests: int
    low_stock_alerts: int


# ─────────────────────────── Graph ───────────────────────────
class GraphNode(BaseModel):
    id: int
    label: str
    type: ItemType
    state: ItemState
    card_type: CardType | None = None


class GraphEdge(BaseModel):
    source: int
    target: int


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ─────────────────────────── Bulk operations ───────────────────────────
class BulkAction(str, enum.Enum):
    move = "move"
    state_change = "state_change"
    delete = "delete"
    link = "link"
    unlink = "unlink"


class BulkRequest(BaseModel):
    action: BulkAction
    item_ids: list[int] = Field(min_length=1)
    # move → location_id ; state_change → state (+ note) ; link → parent_id
    location_id: int | None = None
    parent_id: int | None = None
    state: ItemState | None = None
    note: str | None = None


class BulkResult(BaseModel):
    processed: int
    failed: int = 0
    errors: list[str] = Field(default_factory=list)


# ─────────────────────────── Global search ───────────────────────────
class SearchHit(BaseModel):
    kind: str            # "item" | "location" | "user" | "change_request"
    id: int
    title: str
    subtitle: str | None = None
    badge: str | None = None   # e.g. item type / role
    state: ItemState | None = None
    link: str


class SearchResults(BaseModel):
    query: str
    total: int
    items: list[SearchHit] = Field(default_factory=list)
    locations: list[SearchHit] = Field(default_factory=list)
    users: list[SearchHit] = Field(default_factory=list)
