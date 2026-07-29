"""Excel import/export of items (requirement §11), built on openpyxl."""

from __future__ import annotations

import io
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from lattice_core.models import (
    CardType,
    CatalogCategory,
    CatalogOption,
    Item,
    ItemState,
    ItemType,
    Location,
    StorageStatus,
    User,
)
from lattice_core.services.items import create_item

# Column order for both templates and exports.
COLUMNS = [
    "type", "name", "industry", "project", "team", "state",
    "card_type", "responsible", "lead", "production_date", "version",
    "serial", "storage_status", "location", "parent_id", "description", "dmz",
]


def _enum(value, enum_cls, field: str):
    if value in (None, ""):
        return None
    try:
        return enum_cls(str(value).strip().lower())
    except ValueError as exc:
        allowed = ", ".join(e.value for e in enum_cls)
        raise ValueError(f"Invalid {field} '{value}'. Allowed: {allowed}") from exc


def _to_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date '{value}' (use YYYY-MM-DD)")


# ─────────────────────────── template ───────────────────────────
def build_template(item_type: ItemType | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "items"
    ws.append(COLUMNS)
    example = {
        "type": (item_type.value if item_type else "card"),
        "name": "Example card",
        "industry": "Avionics",
        "project": "Falcon",
        "team": "HW-Team-A",
        "state": "built",
        "card_type": "company",
        "responsible": "Dana",
        "lead": "Noa",
        "production_date": "2025-03-01",
        "version": "1.2",
        "serial": "SN-0001",
        "storage_status": "desiccator",
        "location": "Lab A - Shelf 1",
        "parent_id": "",
        "description": "Free text",
        "dmz": "Detailed status",
    }
    ws.append([example[c] for c in COLUMNS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ─────────────────────────── import ───────────────────────────
def import_items(db: Session, content: bytes, user: User) -> dict:
    wb = load_workbook(io.BytesIO(content), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"created": 0, "errors": []}

    header = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
    created = 0
    errors: list[dict] = []
    # cache locations by name
    loc_cache = {loc.name: loc for loc in db.query(Location).all()}
    # cache known catalog values; unknown project/industry values are registered
    # on the fly (mirrors location auto-creation) so bulk import stays frictionless.
    catalog_cache: set[tuple[CatalogCategory, str]] = {
        (o.category, o.value) for o in db.query(CatalogOption).all()
    }

    def ensure_catalog(category: CatalogCategory, value: str | None) -> str | None:
        if not value:
            return None
        v = str(value).strip()
        if not v:
            return None
        if (category, v) not in catalog_cache:
            db.add(CatalogOption(category=category, value=v))
            db.flush()
            catalog_cache.add((category, v))
        return v

    for idx, raw in enumerate(rows[1:], start=2):
        record = dict(zip(header, raw, strict=False))
        if not record.get("name"):
            continue
        try:
            loc_name = (record.get("location") or "").strip() or None
            location_id = None
            if loc_name:
                loc = loc_cache.get(loc_name)
                if loc is None:
                    loc = Location(name=loc_name)
                    db.add(loc)
                    db.flush()
                    loc_cache[loc_name] = loc
                location_id = loc.id

            data = {
                "type": _enum(record.get("type"), ItemType, "type") or ItemType.card,
                "name": str(record["name"]).strip(),
                "industry": ensure_catalog(
                    CatalogCategory.industry, record.get("industry")
                ),
                "project": ensure_catalog(CatalogCategory.project, record.get("project")),
                "team": record.get("team") or None,
                "state": _enum(record.get("state"), ItemState, "state")
                or ItemState.production,
                "description": record.get("description") or None,
                "dmz": record.get("dmz") or None,
                "card_type": _enum(record.get("card_type"), CardType, "card_type"),
                "responsible": record.get("responsible") or None,
                "lead": record.get("lead") or None,
                "production_date": _to_date(record.get("production_date")),
                "version": (
                    str(record["version"]).strip() if record.get("version") else None
                ),
                "serial": (
                    str(record["serial"]).strip() if record.get("serial") else None
                ),
                "storage_status": _enum(
                    record.get("storage_status"), StorageStatus, "storage_status"
                ),
                "location_id": location_id,
                "parent_id": (
                    int(record["parent_id"]) if record.get("parent_id") else None
                ),
                "manager_ids": [],
            }
            create_item(db, data, user)
            created += 1
        except Exception as exc:  # noqa: BLE001 - collect per-row errors
            errors.append({"row": idx, "error": str(exc)})

    if errors and created == 0:
        db.rollback()
    else:
        db.commit()
    return {"created": created, "errors": errors}


# ─────────────────────────── export ───────────────────────────
def export_items(db: Session, item_type: ItemType | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "items"
    ws.append(COLUMNS + ["id", "location_id", "parent_id_out"])

    q = db.query(Item).filter(Item.is_template.is_(False))
    if item_type is not None:
        q = q.filter(Item.type == item_type)

    for it in q.order_by(Item.type, Item.name).all():
        ws.append([
            it.type.value,
            it.name,
            it.industry,
            it.project,
            it.team,
            it.state.value,
            it.card_type.value if it.card_type else None,
            it.responsible,
            it.lead,
            it.production_date.isoformat() if it.production_date else None,
            it.version,
            it.serial,
            it.storage_status.value if it.storage_status else None,
            it.location.name if it.location else None,
            it.parent_id,
            it.description,
            it.dmz,
            it.id,
            it.location_id,
            it.parent_id,
        ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
