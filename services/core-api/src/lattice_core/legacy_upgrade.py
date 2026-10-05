"""One-time conversion of a pre-migration database to the template model.

Before Alembic, the schema came from ``create_all`` and an item carried its own
name, card type and free-text project/industry/team. The template model changes
that shape fundamentally, so a database from that era cannot simply be
``ALTER``-ed. Instead, in **one transaction**:

1. every legacy row is read into memory;
2. the legacy tables (and, on PostgreSQL, their native enum types) are dropped;
3. the current schema is created by running the migrations to head;
4. the rows are written back in the new shape.

Any failure rolls the whole thing back and leaves the legacy database untouched.

How old data maps onto the new model
------------------------------------
* One template per distinct ``(type, name, card type)``. Its serial prefix is
  taken from the name's Latin letters (padded/deduplicated), and it gets fields
  for everything the old items recorded: industry/project/team, managers,
  description, DAMATZ, version, production date, lead, the old free-text
  "responsible", the old serial, and quantity for commercial cards.
* Items keep their ids (so history, audit and proposals keep pointing at them)
  and get a fresh serial ``T-XXX-###``; the old serial is kept in a field.
* States: production/built → built, used/working → ok, faulty → faulty.
  Card types: unique → copied, company → house, commercial → commercial.
* Old "template" items become templates' descriptions and are not items.
* Locations that held desiccator cards (or are named so) join the desiccator.
* Pending change requests are closed: their payloads describe the old shape and
  could not be applied. Thresholds move onto their card's template.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import MetaData, inspect, select, text
from sqlalchemy.engine import Connection

from lattice_core.database import Base
from lattice_core.models import SERIAL_TYPE_LETTER, ItemType

logger = logging.getLogger("lattice_core.legacy_upgrade")

_LEGACY_TABLES = [
    "item_managers", "state_history", "documents", "extra_items", "change_requests",
    "audit_log", "stock_thresholds", "items", "catalog_options", "map_buildings",
    "locations", "users",
]
# Native enum types SQLAlchemy created on PostgreSQL for the legacy schema.
_LEGACY_PG_TYPES = [
    "itemtype", "cardtype", "itemstate", "storagestatus", "userrole",
    "changestatus", "changeaction", "catalogcategory",
]

_STATE_MAP = {
    "production": "built", "built": "built", "used": "ok", "working": "ok",
    "faulty": "faulty",
}
_CARD_TYPE_MAP = {"unique": "copied", "company": "house", "commercial": "commercial"}

_CLOSED_NOTE = (
    "Closed automatically by the upgrade to template-based items: this proposal "
    "describes the old item format and cannot be applied. Please resubmit it."
)


def needs_upgrade(conn: Connection) -> bool:
    """A legacy database has an ``items`` table with a ``name`` column and no
    Alembic bookkeeping."""
    insp = inspect(conn)
    tables = set(insp.get_table_names())
    if "alembic_version" in tables or "items" not in tables:
        return False
    return "name" in {c["name"] for c in insp.get_columns("items")}


# ─────────────────────────── helpers ───────────────────────────
def _dt(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value.date() if isinstance(value, datetime) else value
    return date.fromisoformat(str(value)[:10])


def _bool(value, default: bool = False) -> bool:
    return default if value is None else bool(value)


def _rows(conn: Connection, table: str, tables: set[str]) -> list[dict]:
    if table not in tables:
        return []
    return [dict(r) for r in conn.execute(text(f"SELECT * FROM {table}")).mappings()]


def _clean(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


class _PrefixPool:
    """Three-letter serial prefixes, unique per item type."""

    def __init__(self) -> None:
        self.used: dict[str, set[str]] = defaultdict(set)

    def take(self, item_type: str, name: str) -> str:
        letters = re.sub(r"[^A-Z]", "", name.upper())
        base = (letters + "XXX")[:3]
        used = self.used[item_type]
        candidate = base
        n = 0
        while candidate in used:
            # Keep the first letter recognisable, roll the other two.
            n += 1
            candidate = base[0] + chr(65 + (n // 26) % 26) + chr(65 + n % 26)
            if n > 26 * 26:
                raise RuntimeError(f"Ran out of serial prefixes for {item_type}")
        used.add(candidate)
        return candidate


# ─────────────────────────── conversion ───────────────────────────
def run(conn: Connection) -> None:
    from lattice_core.seed import upgrade_schema

    logger.warning("Legacy (pre-migration) database detected — converting it.")
    tables = set(inspect(conn).get_table_names())
    data = {t: _rows(conn, t, tables) for t in _LEGACY_TABLES}

    # Drop the legacy schema (FK order handled by reflection).
    legacy = MetaData()
    legacy.reflect(bind=conn, only=[t for t in _LEGACY_TABLES if t in tables])
    legacy.drop_all(bind=conn)
    if conn.dialect.name == "postgresql":
        for type_name in _LEGACY_PG_TYPES:
            conn.execute(text(f"DROP TYPE IF EXISTS {type_name}"))

    upgrade_schema(conn)
    _write(conn, data)
    if conn.dialect.name == "postgresql":
        _reset_sequences(conn)
    logger.warning("Legacy database converted to the template model.")


def _write(conn: Connection, data: dict[str, list[dict]]) -> None:  # noqa: C901
    T = Base.metadata.tables

    # ── users ──
    users = [
        {
            "id": u["id"], "email": u["email"], "full_name": u["full_name"],
            "hashed_password": u["hashed_password"], "role": u["role"],
            "is_active": _bool(u.get("is_active"), True),
            "created_at": _dt(u.get("created_at")) or datetime.now(UTC),
            "login_hint_visible": _bool(u.get("login_hint_visible")),
            "login_hint_password": u.get("login_hint_password"),
        }
        for u in data["users"]
    ]
    if users:
        conn.execute(T["users"].insert(), users)
    user_ids = {u["id"] for u in users}

    # ── locations (names become unique; desiccator membership inferred) ──
    desiccator_locs = {
        i["location_id"]
        for i in data["items"]
        if i.get("storage_status") == "desiccator" and i.get("location_id")
    }
    seen_names: set[str] = set()
    locations = []
    for loc in data["locations"]:
        name = (loc["name"] or f"Location {loc['id']}").strip()
        if name.lower() in seen_names:
            name = f"{name} (#{loc['id']})"
        seen_names.add(name.lower())
        locations.append({
            "id": loc["id"], "name": name, "building": loc.get("building"),
            "room": loc.get("room"), "x": loc.get("x") or 50.0, "y": loc.get("y") or 50.0,
            "notes": loc.get("notes"),
            "is_desiccator": loc["id"] in desiccator_locs
            or bool(re.search(r"desiccator|דסיקטור", name, re.IGNORECASE)),
        })
    if locations:
        conn.execute(T["locations"].insert(), locations)
    location_ids = {loc["id"] for loc in locations}

    buildings = [
        {
            "id": b["id"], "name": b["name"], "x": b["x"], "y": b["y"],
            "width": b["width"], "height": b["height"], "color": b.get("color"),
            "notes": b.get("notes"), "sort_order": b.get("sort_order") or 0,
            "created_at": _dt(b.get("created_at")) or datetime.now(UTC),
        }
        for b in data["map_buildings"]
    ]
    if buildings:
        conn.execute(T["map_buildings"].insert(), buildings)

    # ── catalog (existing values + every team/project/industry items used) ──
    catalog: dict[tuple[str, str], int] = {}
    for o in data["catalog_options"]:
        conn.execute(T["catalog_options"].insert().values(
            id=o["id"], category=o["category"], value=o["value"],
            description=o.get("description"), active=_bool(o.get("active"), True),
            sort_order=o.get("sort_order") or 0,
            created_at=_dt(o.get("created_at")) or datetime.now(UTC),
        ))
        catalog[(o["category"], o["value"])] = o["id"]

    def option_id(category: str, value) -> int | None:
        v = _clean(value)
        if v is None:
            return None
        key = (category, v)
        if key not in catalog:
            result = conn.execute(T["catalog_options"].insert().values(
                category=category, value=v, active=True, sort_order=0,
                created_at=datetime.now(UTC),
            ))
            catalog[key] = result.inserted_primary_key[0]
        return catalog[key]

    # ── templates: one per (type, name, card type) ──
    prefixes = _PrefixPool()
    templates: dict[tuple, dict] = {}

    def template_key(row: dict) -> tuple:
        card_type = None
        if row["type"] == "card":
            card_type = _CARD_TYPE_MAP.get(row.get("card_type") or "", "house")
        return (row["type"], (row["name"] or "").strip() or f"Item {row['id']}", card_type)

    for row in sorted(data["items"], key=lambda r: (bool(r.get("is_template")), r["id"])):
        key = template_key(row)
        if key not in templates:
            item_type, name, card_type = key
            result = conn.execute(T["item_templates"].insert().values(
                type=item_type, name=name, card_type=card_type,
                serial_prefix=prefixes.take(item_type, name),
                description=_clean(row.get("description")) if row.get("is_template") else None,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
            ))
            tid = result.inserted_primary_key[0]
            templates[key] = {"id": tid, "fields": _create_fields(conn, tid, item_type, card_type)}
        elif row.get("is_template") and _clean(row.get("description")):
            # An old "template" item is the best description of its kind.
            conn.execute(
                T["item_templates"].update()
                .where(T["item_templates"].c.id == templates[key]["id"])
                .where(T["item_templates"].c.description.is_(None))
                .values(description=_clean(row.get("description")))
            )

    # ── items ──
    live = [r for r in data["items"] if not r.get("is_template")]
    live_ids = {r["id"] for r in live}
    counters: dict[int, int] = defaultdict(int)
    template_of: dict[int, dict] = {}
    for row in sorted(live, key=lambda r: r["id"]):
        tpl = templates[template_key(row)]
        template_of[row["id"]] = tpl
        counters[tpl["id"]] += 1
        prefix = conn.execute(
            select(T["item_templates"].c.serial_prefix).where(
                T["item_templates"].c.id == tpl["id"]
            )
        ).scalar_one()
        serial = f"{SERIAL_TYPE_LETTER[ItemType(row['type'])]}-{prefix}-{counters[tpl['id']]:03d}"
        conn.execute(T["items"].insert().values(
            id=row["id"], template_id=tpl["id"], type=row["type"], serial=serial,
            state=_STATE_MAP.get(row.get("state") or "", "built"),
            parent_id=None,  # second pass: parents may come later in id order
            location_id=row.get("location_id") if row.get("location_id") in location_ids else None,
            quantity=max(int(row.get("quantity") or 1), 1),
            industry_id=option_id("industry", row.get("industry")),
            project_id=option_id("project", row.get("project")),
            team_id=option_id("team", row.get("team")),
            created_at=_dt(row.get("created_at")) or datetime.now(UTC),
            updated_at=_dt(row.get("updated_at")) or datetime.now(UTC),
        ))
        values = {
            "description": _clean(row.get("description")),
            "dmz": _clean(row.get("dmz")),
            "version": _clean(row.get("version")),
            "production_date": (
                _date(row.get("production_date")).isoformat()
                if row.get("production_date") else None
            ),
            "lead": _clean(row.get("lead")),
            "legacy_responsible": _clean(row.get("responsible")),
            "legacy_serial": _clean(row.get("serial")),
        }
        for key, value in values.items():
            field_id = tpl["fields"].get(key)
            if field_id is not None and value is not None:
                conn.execute(T["item_field_values"].insert().values(
                    item_id=row["id"], field_id=field_id, value=value
                ))
    for row in live:
        if row.get("parent_id") in live_ids:
            conn.execute(
                T["items"].update().where(T["items"].c.id == row["id"])
                .values(parent_id=row["parent_id"])
            )

    # ── dependants of items ──
    managers = [
        m for m in data["item_managers"]
        if m["item_id"] in live_ids and m["user_id"] in user_ids
    ]
    if managers:
        conn.execute(T["item_managers"].insert(), managers)

    history = [
        {
            "id": h["id"], "item_id": h["item_id"],
            "state": _STATE_MAP.get(h.get("state") or "", "built"), "note": h.get("note"),
            "changed_by": h.get("changed_by") if h.get("changed_by") in user_ids else None,
            "changed_at": _dt(h.get("changed_at")) or datetime.now(UTC),
        }
        for h in data["state_history"]
        if h["item_id"] in live_ids
    ]
    if history:
        conn.execute(T["state_history"].insert(), history)

    template_by_item = {r["id"]: templates[template_key(r)]["id"] for r in data["items"]}
    for d in data["documents"]:
        on_item = d["item_id"] in live_ids
        conn.execute(T["documents"].insert().values(
            id=d["id"],
            item_id=d["item_id"] if on_item else None,
            template_id=None if on_item else template_by_item.get(d["item_id"]),
            name=d["name"], doc_type=d.get("doc_type"), url=d.get("url") or "",
            created_at=datetime.now(UTC),
        ))

    extras = [
        {
            "id": e["id"], "setup_id": e["setup_id"], "name": e["name"],
            "company_part_number": e.get("company_part_number"), "serial": e.get("serial"),
            "signed_by": e.get("signed_by"),
        }
        for e in data["extra_items"]
        if e["setup_id"] in live_ids
    ]
    if extras:
        conn.execute(T["extra_items"].insert(), extras)

    for cr in data["change_requests"]:
        pending = cr.get("status") == "pending"
        conn.execute(T["change_requests"].insert().values(
            id=cr["id"], action=cr["action"],
            item_id=cr["item_id"] if cr.get("item_id") in live_ids else None,
            item_type=cr.get("item_type"), item_name=cr.get("item_name"),
            payload=cr.get("payload") or {}, description=cr["description"],
            reason=cr["reason"], status="rejected" if pending else cr["status"],
            proposed_by=cr["proposed_by"],
            reviewed_by=cr.get("reviewed_by") if cr.get("reviewed_by") in user_ids else None,
            review_note=_CLOSED_NOTE if pending else cr.get("review_note"),
            created_at=_dt(cr.get("created_at")) or datetime.now(UTC),
            reviewed_at=datetime.now(UTC) if pending else _dt(cr.get("reviewed_at")),
        ))

    audit = [
        {
            "id": a["id"],
            "item_id": a["item_id"] if a.get("item_id") in live_ids else None,
            "item_name": a.get("item_name"), "action": a["action"], "summary": a["summary"],
            "details": a.get("details") or {},
            "user_id": a.get("user_id") if a.get("user_id") in user_ids else None,
            "user_name": a.get("user_name"),
            "created_at": _dt(a.get("created_at")) or datetime.now(UTC),
        }
        for a in data["audit_log"]
    ]
    if audit:
        conn.execute(T["audit_log"].insert(), audit)

    thresholds: dict[int, dict] = {}
    for t in data["stock_thresholds"]:
        key = ("card", (t.get("name") or "").strip(),
               _CARD_TYPE_MAP.get(t.get("card_type") or "", "house"))
        tpl = templates.get(key)
        if tpl is None:
            continue
        current = thresholds.get(tpl["id"])
        if current is None or (t.get("min_quantity") or 0) > current["min_quantity"]:
            thresholds[tpl["id"]] = {
                "template_id": tpl["id"], "min_quantity": t.get("min_quantity") or 0,
                "editor_email": t.get("editor_email"),
            }
    if thresholds:
        conn.execute(T["stock_thresholds"].insert(), list(thresholds.values()))


def _create_fields(
    conn: Connection, template_id: int, item_type: str, card_type: str | None
) -> dict[str, int]:
    """The fields a converted template needs to hold everything legacy items had."""
    T = Base.metadata.tables
    specs: list[tuple[str, str, str]] = [
        ("industry", "Industry", "industry"),
        ("project", "Project", "project"),
        ("team", "Team", "team"),
        ("managers", "Managers", "managers"),
        ("description", "Description", "text"),
        ("dmz", 'DAMATZ (דמ"צ)', "text"),
    ]
    if item_type == "card":
        specs += [
            ("version", "Version", "string"),
            ("production_date", "Production date", "date"),
            ("lead", "Lead", "string"),
            ("legacy_responsible", "Responsible (legacy)", "string"),
            ("legacy_serial", "Legacy serial", "serial_string"),
        ]
        if card_type == "commercial":
            specs.append(("quantity", "Quantity", "quantity"))
    ids: dict[str, int] = {}
    for position, (key, label, field_type) in enumerate(specs):
        result = conn.execute(T["template_fields"].insert().values(
            template_id=template_id, key=key, label=label, field_type=field_type,
            mode="item", required=False, position=position, config={}, fixed_value=None,
        ))
        ids[key] = result.inserted_primary_key[0]
    return ids


def _reset_sequences(conn: Connection) -> None:
    """Rows were inserted with explicit ids; move each sequence past them."""
    for table in Base.metadata.sorted_tables:
        if "id" not in table.c or not table.c.id.autoincrement:
            continue
        conn.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table.name}), 0) + 1, false)"
        ))
