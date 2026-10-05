"""Pydantic (v2) request/response schemas."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from lattice_core.models import (
    CardTracking,
    CardType,
    CatalogCategory,
    ChangeAction,
    ChangeStatus,
    FieldMode,
    FieldType,
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
    name: str = Field(min_length=1, max_length=255)
    building: str | None = None
    room: str | None = None
    x: float = Field(default=50.0, ge=0, le=100)
    y: float = Field(default=50.0, ge=0, le=100)
    notes: str | None = None
    is_desiccator: bool = False


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    building: str | None = None
    room: str | None = None
    x: float | None = Field(default=None, ge=0, le=100)
    y: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = None
    is_desiccator: bool | None = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    building: str | None = None
    room: str | None = None
    x: float
    y: float
    notes: str | None = None
    is_desiccator: bool = False
    item_count: int = 0


class DesiccatorUpdate(BaseModel):
    """The full set of locations that make up the desiccator."""

    location_ids: list[int] = Field(default_factory=list)


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


# ─────────────────────────── Catalog ───────────────────────────
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
    # Ids of the values (of other categories) this one is linked to.
    linked_ids: list[int] = Field(default_factory=list)


class CatalogLinksUpdate(BaseModel):
    """The option's links to one other category, after the edit."""

    category: CatalogCategory
    option_ids: list[int] = Field(default_factory=list)


class CatalogLinkOut(BaseModel):
    a_id: int
    b_id: int


# ─────────────────────────── Templates ───────────────────────────
class TemplateFieldIn(BaseModel):
    id: int | None = None
    key: str | None = None
    label: str = Field(min_length=1, max_length=255)
    field_type: FieldType
    mode: FieldMode = FieldMode.item
    required: bool = False
    config: dict = Field(default_factory=dict)
    fixed_value: Any = None


class TemplateCreate(BaseModel):
    type: ItemType
    name: str = Field(min_length=1, max_length=255)
    card_type: CardType | None = None
    serial_prefix: str = Field(min_length=3, max_length=3)
    description: str | None = None
    fields: list[TemplateFieldIn] = Field(default_factory=list)
    child_template_ids: list[int] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    card_type: CardType | None = None
    serial_prefix: str | None = Field(default=None, min_length=3, max_length=3)
    description: str | None = None
    # When given: the template's complete field list after the edit (fields
    # missing from it are removed; `id` marks an existing field).
    fields: list[TemplateFieldIn] | None = None
    child_template_ids: list[int] | None = None


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    doc_type: str | None = None
    url: str | None = None
    is_file: bool = False
    original_filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    field_id: int | None = None
    created_at: datetime | None = None


class TemplateFieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    label: str
    field_type: FieldType
    mode: FieldMode
    required: bool
    position: int
    config: dict
    fixed_value: Any = None
    # Human-readable rendering of fixed_value (names instead of ids).
    fixed_display: Any = None
    # Labels for a list field's options, in order (same length as options).
    options_display: list[str] = Field(default_factory=list)
    files: list[DocumentOut] = Field(default_factory=list)


class TemplateBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: ItemType
    name: str
    card_type: CardType | None = None
    serial_prefix: str


class TemplateCounts(BaseModel):
    """Units per state, destroyed excluded (they are history, not inventory)."""

    built: int = 0
    ok: int = 0
    faulty: int = 0
    total: int = 0
    destroyed: int = 0


class TemplateSummary(TemplateBrief):
    tracking: CardTracking | None = None
    description: str | None = None
    counts: TemplateCounts = Field(default_factory=TemplateCounts)
    child_template_ids: list[int] = Field(default_factory=list)
    parent_template_ids: list[int] = Field(default_factory=list)
    field_count: int = 0
    updated_at: datetime | None = None


class TemplateOut(TemplateSummary):
    fields: list[TemplateFieldOut] = Field(default_factory=list)
    child_templates: list[TemplateBrief] = Field(default_factory=list)
    parent_templates: list[TemplateBrief] = Field(default_factory=list)
    next_serial: str | None = None
    created_at: datetime | None = None


# ─────────────────────────── Items ───────────────────────────
class StateHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    state: ItemState
    note: str | None
    changed_by: int | None
    changed_by_name: str | None = None
    changed_at: datetime


class ExtraItemCreate(BaseModel):
    name: str
    company_part_number: str | None = None
    serial: str | None = None
    signed_by: str | None = None


class ExtraItemOut(ExtraItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class CatalogRef(BaseModel):
    id: int
    value: str


class ItemBrief(BaseModel):
    id: int
    type: ItemType
    template_id: int
    name: str
    serial: str
    state: ItemState
    card_type: CardType | None = None
    location_id: int | None = None


class ItemFieldOut(BaseModel):
    field_id: int
    key: str
    label: str
    field_type: FieldType
    mode: FieldMode
    required: bool
    config: dict = Field(default_factory=dict)
    value: Any = None
    # Human-readable rendering: names for ids, files as documents.
    display: Any = None
    missing: bool = False


class ItemListOut(BaseModel):
    """Compact representation for list/table views."""

    id: int
    type: ItemType
    template_id: int
    name: str
    serial: str
    state: ItemState
    card_type: CardType | None = None
    quantity: int = 1
    storage_status: StorageStatus | None = None
    parent_id: int | None = None
    parent_label: str | None = None
    location_id: int | None = None
    location_name: str | None = None
    industry: str | None = None
    project: str | None = None
    team: str | None = None
    children_count: int = 0
    manager_names: list[str] = Field(default_factory=list)
    updated_at: datetime


class ItemCreate(BaseModel):
    template_id: int
    # {field key: value} for the template's per-item and list fields.
    values: dict[str, Any] = Field(default_factory=dict)
    # Leave empty to get the next serial of the template.
    serial: str | None = None
    # Existing items to place inside the new one.
    child_ids: list[int] = Field(default_factory=list)


class ItemUpdate(BaseModel):
    # Only the fields being changed.
    values: dict[str, Any] = Field(default_factory=dict)
    serial: str | None = None


class ItemOut(BaseModel):
    id: int
    type: ItemType
    template: TemplateBrief
    name: str
    serial: str
    state: ItemState
    card_type: CardType | None = None
    tracking: CardTracking | None = None
    quantity: int = 1
    storage_status: StorageStatus | None = None
    parent_id: int | None = None
    location_id: int | None = None
    location: LocationOut | None = None
    parent: ItemBrief | None = None
    children: list[ItemBrief] = Field(default_factory=list)
    industry: CatalogRef | None = None
    project: CatalogRef | None = None
    team: CatalogRef | None = None
    responsible: UserBrief | None = None
    managers: list[UserBrief] = Field(default_factory=list)
    fields: list[ItemFieldOut] = Field(default_factory=list)
    state_history: list[StateHistoryOut] = Field(default_factory=list)
    documents: list[DocumentOut] = Field(default_factory=list)
    extra_items: list[ExtraItemOut] = Field(default_factory=list)
    # Templates whose items may be placed inside this one.
    child_templates: list[TemplateBrief] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MoveRequest(BaseModel):
    location_id: int
    note: str | None = None


class LinkRequest(BaseModel):
    parent_id: int


class UnlinkRequest(BaseModel):
    # Where the item now physically is; defaults to its container's location.
    location_id: int | None = None


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
    template_id: int | None = None
    item_type: ItemType | None = None
    payload: dict = Field(default_factory=dict)
    # What changes — filled in from the action when left empty.
    description: str | None = None
    reason: str = Field(min_length=1)


class ChangeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action: ChangeAction
    item_id: int | None
    template_id: int | None = None
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
    template_id: int | None = None
    item_name: str | None
    action: str
    summary: str
    details: dict
    user_id: int | None
    user_name: str | None
    created_at: datetime


# ─────────────────────────── Inventory ───────────────────────────
class ThresholdCreate(BaseModel):
    template_id: int
    min_quantity: int = Field(default=0, ge=0)
    editor_email: EmailStr | None = None


class ThresholdOut(BaseModel):
    id: int
    template_id: int
    name: str
    card_type: CardType | None = None
    tracking: CardTracking | None = None
    min_quantity: int = 0
    editor_email: EmailStr | None = None
    # Units available for building: loose, at a desiccator location, built/ok.
    current_quantity: int = 0
    is_low: bool = False


class InventoryGroup(BaseModel):
    """Stock of one card template."""

    template_id: int
    name: str
    card_type: CardType
    tracking: CardTracking | None = None
    serial_prefix: str
    total: int            # every unit except destroyed ones
    available: int        # desiccator + loose + built/ok — what can be built with
    desiccator: int       # loose at a desiccator location (any non-destroyed state)
    in_use: int           # loose outside the desiccator
    assembled: int        # inside an assembly or setup
    faulty: int
    records: int = 0
    available_serials: list[str] = Field(default_factory=list)
    min_quantity: int | None = None
    is_low: bool = False


class InventorySummary(BaseModel):
    setups: int
    assemblies: int
    cards: int
    cards_in_use: int
    cards_desiccator: int
    cards_available: int
    faulty_items: int
    pending_change_requests: int
    low_stock_alerts: int
    templates: int = 0


# ─────────────────────────── Graph ───────────────────────────
class GraphNode(BaseModel):
    id: int
    label: str
    type: ItemType
    state: ItemState | None = None
    card_type: CardType | None = None
    serial: str | None = None
    template_id: int | None = None
    # Template graph: how many live items the template has.
    count: int | None = None


class GraphEdge(BaseModel):
    source: int
    target: int


class GraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    # Trees of live items drawn: their root ids.
    roots: list[int] = Field(default_factory=list)


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
    kind: str            # "item" | "template" | "location" | "user"
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
    templates: list[SearchHit] = Field(default_factory=list)
    locations: list[SearchHit] = Field(default_factory=list)
    users: list[SearchHit] = Field(default_factory=list)


# ─────────────────────────── Import ───────────────────────────
class ImportCellError(BaseModel):
    sheet: str
    cell: str | None = None
    row: int | None = None
    column: str | None = None
    error: str


class ImportResult(BaseModel):
    created: int
    by_template: dict[str, int] = Field(default_factory=dict)
    errors: list[ImportCellError] = Field(default_factory=list)
