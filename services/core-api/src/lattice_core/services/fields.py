"""Template fields: validating their definitions and the values items give them.

Two jobs live here, kept together because they must agree:

* ``normalize_field_specs`` — checks the fields a template author defines
  (types, modes, lists, formats, fixed values) and assigns stable keys.
* ``coerce_value`` — turns whatever a form, a proposal or a spreadsheet cell
  supplied into the canonical stored value for a field, or explains precisely
  why it can't.

Reference types (catalog values, users, locations, items, documents) are stored
by id and checked against the database here, so a value that reaches a row is
always one that existed when it was written.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from lattice_core.errors import DomainError
from lattice_core.models import (
    CATALOG_FIELD_TYPES,
    PER_UNIT_FIELD_TYPES,
    SYSTEM_FIELD_TYPES,
    CardTracking,
    CardType,
    CatalogOption,
    Document,
    FieldMode,
    FieldType,
    ItemState,
    ItemType,
    Location,
    TemplateField,
    User,
    UserRole,
    card_tracking,
)

DEFAULT_DESCRIPTION_MIN = 8
_LETTERS = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$")
_KEY_RE = re.compile(r"[^a-z0-9]+")

# Field types whose value is a list (everything else is a scalar).
MULTI_VALUE_TYPES = frozenset({FieldType.managers, FieldType.files})

# Field types that refer to other rows by id.
REFERENCE_TYPES = frozenset({
    FieldType.industry, FieldType.project, FieldType.team, FieldType.managers,
    FieldType.responsible, FieldType.location, FieldType.parent, FieldType.files,
})

# Types a template of each item type may not use.
_FORBIDDEN_BY_ITEM_TYPE: dict[ItemType, frozenset[FieldType]] = {
    # A setup is always top of the tree and is never counted in units.
    ItemType.setup: frozenset({FieldType.parent, FieldType.quantity}),
    ItemType.assembly: frozenset({FieldType.quantity}),
    ItemType.card: frozenset(),
}


# ─────────────────────────── formats ───────────────────────────
def pattern_slots(pattern: str) -> int:
    return pattern.count("#")


def apply_pattern(pattern: str, raw: str) -> str:
    """Fill a ``XX-#####`` format: ``#`` is a digit the user types, everything
    else is filled in automatically.

    Accepts either just the digits (``"12345"``) or the complete value
    (``"XX-12345"``), and always returns the complete value.
    """
    raw = raw.strip()
    regex = "^" + "".join(r"\d" if ch == "#" else re.escape(ch) for ch in pattern) + "$"
    if re.match(regex, raw):
        return raw
    digits = re.sub(r"\s", "", raw)
    slots = pattern_slots(pattern)
    if not digits.isdigit() or len(digits) != slots:
        raise ValueError(
            f"expected {slots} digit(s) for the format '{pattern}' "
            f"(the other characters are filled in automatically)"
        )
    it = iter(digits)
    return "".join(next(it) if ch == "#" else ch for ch in pattern)


# ─────────────────────────── keys ───────────────────────────
def make_key(label: str, taken: set[str]) -> str:
    base = _KEY_RE.sub("_", label.lower()).strip("_")[:48] or "field"
    if base[0].isdigit():
        base = f"f_{base}"
    key, n = base, 2
    while key in taken:
        key = f"{base}_{n}"
        n += 1
    return key


# ─────────────────────────── value coercion ───────────────────────────
def is_empty(value) -> bool:
    return value is None or value == "" or value == []


def _as_int(value, what: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"expected {what}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"expected {what}") from None


def _as_id_list(value) -> list[int]:
    if isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [v for v in re.split(r"[,;]", str(value)) if v.strip()]
    out: list[int] = []
    for v in items:
        i = _as_int(v, "a list of ids")
        if i not in out:
            out.append(i)
    return out


def coerce_value(  # noqa: C901 - one branch per field type is the clearest shape
    db: Session,
    field_type: FieldType,
    value,
    config: dict | None = None,
):
    """Canonical stored value for one field, or ``ValueError`` with the reason.

    ``None``/empty passes through as ``None`` — whether that is allowed is the
    caller's decision (the field may be optional).
    """
    config = config or {}
    if is_empty(value):
        return None

    if field_type in (FieldType.text,):
        return str(value).strip() or None

    if field_type == FieldType.description:
        text = str(value).strip()
        minimum = int(config.get("min_length") or DEFAULT_DESCRIPTION_MIN)
        visible = len(re.sub(r"\s", "", text))
        if visible < minimum:
            raise ValueError(
                f"needs at least {minimum} non-blank characters (has {visible})"
            )
        return text

    if field_type in (FieldType.string, FieldType.serial_string):
        text = str(value).strip()
        if isinstance(value, float) and value.is_integer():
            text = str(int(value))  # a spreadsheet's 12345.0
        pattern = config.get("pattern")
        return apply_pattern(pattern, text) if pattern else (text or None)

    if field_type == FieldType.link:
        text = str(value).strip()
        if not _URL_RE.match(text):
            raise ValueError("expected a link such as https://example.com/...")
        return text

    if field_type == FieldType.enum:
        text = str(value).strip()
        options = [str(o) for o in config.get("options") or []]
        if text not in options:
            raise ValueError(f"'{text}' is not one of: {', '.join(options)}")
        return text

    if field_type == FieldType.letter:
        text = str(value).strip().upper()
        if text not in _LETTERS:
            raise ValueError("expected a single letter A–Z")
        return text

    if field_type == FieldType.date:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(text[:10], fmt).date().isoformat()
            except ValueError:
                continue
        raise ValueError("expected a date (YYYY-MM-DD)")

    if field_type == FieldType.integer:
        return _as_int(value, "a whole number")

    if field_type == FieldType.quantity:
        qty = _as_int(value, "a whole number")
        if qty < 1:
            raise ValueError("a quantity must be at least 1")
        return qty

    if field_type == FieldType.decimal:
        if isinstance(value, bool):
            raise ValueError("expected a number")
        try:
            return float(Decimal(str(value).strip()))
        except (InvalidOperation, ValueError):
            raise ValueError("expected a number") from None

    if field_type == FieldType.boolean:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "yes", "1", "y", "כן", "v"):
            return True
        if text in ("false", "no", "0", "n", "לא", "x"):
            return False
        raise ValueError("expected yes/no")

    if field_type == FieldType.status:
        try:
            return ItemState(str(value).strip().lower()).value
        except ValueError:
            allowed = ", ".join(s.value for s in ItemState)
            raise ValueError(f"expected one of: {allowed}") from None

    if field_type in CATALOG_FIELD_TYPES:
        category = CATALOG_FIELD_TYPES[field_type]
        option = _resolve_catalog(db, category, value)
        if option is None:
            raise ValueError(f"'{value}' is not a known {category.value} in the catalog")
        if not option.active:
            raise ValueError(f"the {category.value} '{option.value}' is inactive")
        return option.id

    if field_type == FieldType.managers:
        ids = _resolve_users(db, value)
        managers = {
            u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()
        } if ids else {}
        for uid in ids:
            u = managers.get(uid)
            if u is None or not u.is_active:
                raise ValueError(f"user #{uid} is not an active user")
            if u.role != UserRole.manager:
                raise ValueError(f"{u.full_name} is not a manager")
        return ids or None

    if field_type == FieldType.responsible:
        ids = _resolve_users(db, value)
        if len(ids) != 1:
            raise ValueError("expected exactly one user")
        user = db.get(User, ids[0])
        if user is None or not user.is_active:
            raise ValueError(f"user #{ids[0]} is not an active user")
        return user.id

    if field_type == FieldType.location:
        loc = _resolve_location(db, value)
        if loc is None:
            raise ValueError(f"'{value}' is not a known location")
        return loc.id

    if field_type == FieldType.parent:
        # Existence and fit are checked when linking (services/items.py).
        return _resolve_item_id(db, value)

    if field_type == FieldType.files:
        ids = _as_id_list(value)
        docs = db.query(Document).filter(Document.id.in_(ids)).all() if ids else []
        if len(docs) != len(ids):
            raise ValueError("one or more uploaded files no longer exist")
        return ids

    raise ValueError(f"unsupported field type {field_type}")  # pragma: no cover


def _resolve_catalog(db: Session, category, value) -> CatalogOption | None:
    q = db.query(CatalogOption).filter(CatalogOption.category == category)
    if isinstance(value, int) and not isinstance(value, bool):
        return q.filter(CatalogOption.id == value).first()
    text = str(value).strip()
    option = q.filter(CatalogOption.value == text).first()
    if option is None and text.isdigit():
        option = q.filter(CatalogOption.id == int(text)).first()
    return option


def _resolve_users(db: Session, value) -> list[int]:
    """Ids, or (from a spreadsheet) emails/full names, separated by , or ;."""
    raw = value if isinstance(value, (list, tuple)) else re.split(r"[,;]", str(value))
    out: list[int] = []
    for v in raw:
        if isinstance(v, int) and not isinstance(v, bool):
            uid = v
        else:
            text = str(v).strip()
            if not text:
                continue
            if text.isdigit():
                uid = int(text)
            else:
                user = (
                    db.query(User)
                    .filter((User.email == text) | (User.full_name == text))
                    .first()
                )
                if user is None:
                    raise ValueError(f"'{text}' is not a known user")
                uid = user.id
        if uid not in out:
            out.append(uid)
    return out


def _resolve_location(db: Session, value) -> Location | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return db.get(Location, value)
    text = str(value).strip()
    loc = db.query(Location).filter(Location.name == text).first()
    if loc is None and text.isdigit():
        loc = db.get(Location, int(text))
    return loc


def _resolve_item_id(db: Session, value) -> int:
    from lattice_core.models import Item

    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = str(value).strip()
    item = db.query(Item).filter(Item.serial == text.upper()).first()
    if item is not None:
        return item.id
    if text.isdigit():
        return int(text)
    raise ValueError(f"'{text}' is not a known item serial")


# ─────────────────────────── template field specs ───────────────────────────
def normalize_field_specs(  # noqa: C901
    db: Session,
    item_type: ItemType,
    card_type: CardType | None,
    specs: list[dict],
    existing: dict[int, TemplateField] | None = None,
) -> list[dict]:
    """Validate a template's field list; returns cleaned specs (in order).

    Each spec: ``label``, ``field_type``, ``mode``, ``required``, ``config``,
    ``fixed_value`` and optionally ``id`` (an existing field) / ``key``.
    """
    existing = existing or {}
    out: list[dict] = []
    keys: set[str] = set()
    labels: set[str] = set()
    system_seen: set[FieldType] = set()
    forbidden = _FORBIDDEN_BY_ITEM_TYPE[item_type]

    for position, spec in enumerate(specs):
        label = str(spec.get("label") or "").strip()
        where = f"Field {position + 1}" + (f" ('{label}')" if label else "")
        if not label:
            raise DomainError(f"{where}: a field needs a name")
        if label.lower() in labels:
            raise DomainError(f"{where}: two fields are named '{label}'")
        labels.add(label.lower())

        try:
            field_type = FieldType(spec.get("field_type"))
            mode = FieldMode(spec.get("mode") or FieldMode.item)
        except ValueError as exc:
            raise DomainError(f"{where}: {exc}") from None

        field_id = spec.get("id")
        if field_id is not None:
            current = existing.get(field_id)
            if current is None:
                raise DomainError(f"{where}: field #{field_id} is not part of this template")
            if current.field_type != field_type:
                raise DomainError(
                    f"{where}: a field's type cannot change once it exists — remove "
                    "it and add a new field instead"
                )

        if field_type in forbidden:
            raise DomainError(f"{where}: a {item_type.value} template cannot have a "
                              f"{field_type.value} field")
        counted = card_tracking(card_type) is CardTracking.quantity
        if field_type == FieldType.quantity and not counted:
            raise DomainError(
                f"{where}: only commercial cards are counted by quantity — every other "
                "card is one unit per serial"
            )
        if field_type in SYSTEM_FIELD_TYPES:
            if field_type in system_seen:
                raise DomainError(f"{where}: a template can have only one "
                                  f"{field_type.value} field")
            system_seen.add(field_type)
        if field_type in PER_UNIT_FIELD_TYPES and mode == FieldMode.fixed:
            raise DomainError(
                f"{where}: {field_type.value} describes each unit, so it can be filled "
                "per item or chosen from a list, not fixed for all items"
            )
        if field_type == FieldType.files and mode == FieldMode.choice:
            raise DomainError(f"{where}: a files field cannot be a list")
        if field_type == FieldType.parent and mode == FieldMode.choice:
            raise DomainError(f"{where}: the parent is chosen per item")

        config = _normalize_config(db, field_type, mode, dict(spec.get("config") or {}), where)
        required = bool(spec.get("required"))

        fixed_value = None
        if mode == FieldMode.fixed and field_type != FieldType.files:
            try:
                fixed_value = coerce_value(db, field_type, spec.get("fixed_value"), config)
            except ValueError as exc:
                raise DomainError(f"{where}: {exc}") from None
            if required and is_empty(fixed_value):
                raise DomainError(f"{where}: a required template field needs its value")

        key = (spec.get("key") or "").strip() or (
            existing[field_id].key if field_id is not None else ""
        )
        if not key or key in keys:
            key = make_key(label, keys)
        keys.add(key)

        out.append({
            "id": field_id,
            "key": key,
            "label": label,
            "field_type": field_type,
            "mode": mode,
            "required": required,
            "position": position,
            "config": config,
            "fixed_value": fixed_value,
        })
    return out


def _normalize_config(
    db: Session, field_type: FieldType, mode: FieldMode, config: dict, where: str
) -> dict:
    clean: dict = {}

    if field_type in (FieldType.string, FieldType.serial_string) and config.get("pattern"):
        pattern = str(config["pattern"]).strip()
        if "#" not in pattern:
            raise DomainError(f"{where}: a format needs at least one # (a digit to type)")
        clean["pattern"] = pattern

    if field_type == FieldType.description:
        try:
            minimum = int(config.get("min_length") or DEFAULT_DESCRIPTION_MIN)
        except (TypeError, ValueError):
            raise DomainError(f"{where}: the minimum length must be a number") from None
        if minimum < 1:
            raise DomainError(f"{where}: the minimum length must be at least 1")
        clean["min_length"] = minimum

    if field_type == FieldType.enum:
        options = [str(o).strip() for o in config.get("options") or [] if str(o).strip()]
        if not options:
            raise DomainError(f"{where}: a list needs at least one value")
        if len(set(options)) != len(options):
            raise DomainError(f"{where}: the list repeats a value")
        clean["options"] = options
    elif mode == FieldMode.choice:
        raw = config.get("options") or []
        if not raw:
            raise DomainError(f"{where}: a list field needs at least one value — the "
                              "first one is the default")
        options = []
        for o in raw:
            try:
                coerced = coerce_value(db, field_type, o, clean)
            except ValueError as exc:
                raise DomainError(f"{where}: list value '{o}': {exc}") from None
            # A managers list offers individual managers to pick from.
            for v in coerced if isinstance(coerced, list) else [coerced]:
                if v not in options:
                    options.append(v)
        clean["options"] = options
    return clean


def default_value(field: TemplateField):
    """The value a new item gets when the creator leaves the field alone."""
    if field.mode == FieldMode.fixed:
        return field.fixed_value
    if field.mode == FieldMode.choice:
        options = (field.config or {}).get("options") or []
        if not options:
            return None
        return [options[0]] if field.field_type == FieldType.managers else options[0]
    return None


def check_choice(field: TemplateField, value) -> None:
    """A list field's value must come from the template's list."""
    options = (field.config or {}).get("options") or []
    if field.mode != FieldMode.choice and field.field_type != FieldType.enum:
        return
    values = value if isinstance(value, list) else [value]
    for v in values:
        if v not in options:
            raise ValueError("is not one of the values this template allows")
