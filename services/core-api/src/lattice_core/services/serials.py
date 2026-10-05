"""Item serials: ``C-XXX-###`` (cards), ``A-XXX-###`` (assemblies), ``S-XXX-###``
(setups).

* The letter is the item type; ``XXX`` is the three-letter prefix defined on the
  template; ``###`` is assigned automatically, one above the highest number
  already issued under that prefix (so numbers never collide and are never
  reused while an item holds them). Past 999 it simply grows a digit.
* A serial may be edited by hand. It must keep the scheme — the type's letter
  and the template's prefix — and it must be unique: the database enforces that
  with a unique index, and the check here explains the clash instead of
  surfacing an integrity error.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from lattice_core.errors import DomainError
from lattice_core.models import SERIAL_TYPE_LETTER, Item, ItemTemplate, ItemType

PREFIX_RE = re.compile(r"^[A-Z]{3}$")
SERIAL_RE = re.compile(r"^([CAS])-([A-Z]{3})-(\d{3,})$")


def normalize_prefix(prefix: str | None) -> str:
    value = (prefix or "").strip().upper()
    if not PREFIX_RE.match(value):
        raise DomainError(
            "The serial prefix must be exactly three Latin letters (A–Z), e.g. 'PRB'."
        )
    return value


def format_serial(item_type: ItemType, prefix: str, number: int) -> str:
    return f"{SERIAL_TYPE_LETTER[item_type]}-{prefix}-{number:03d}"


def next_serial(db: Session, template: ItemTemplate) -> str:
    """One above the highest number issued under this type + prefix."""
    head = f"{SERIAL_TYPE_LETTER[template.type]}-{template.serial_prefix}-"
    serials = [
        s for (s,) in db.query(Item.serial).filter(Item.serial.like(f"{head}%")).all()
    ]
    highest = 0
    for s in serials:
        m = SERIAL_RE.match(s)
        if m:
            highest = max(highest, int(m.group(3)))
    return format_serial(template.type, template.serial_prefix, highest + 1)


def validate_manual(
    db: Session,
    template: ItemTemplate,
    serial: str,
    item: Item | None = None,
) -> str:
    """A hand-typed serial: right scheme, right type, right template, unique."""
    value = (serial or "").strip().upper()
    m = SERIAL_RE.match(value)
    letter = SERIAL_TYPE_LETTER[template.type]
    example = format_serial(template.type, template.serial_prefix, 1)
    if not m:
        raise DomainError(f"'{serial}' is not a valid serial — expected the form {example}")
    if m.group(1) != letter:
        raise DomainError(
            f"A {template.type.value} serial starts with '{letter}-' (e.g. {example})"
        )
    allowed_prefixes = {template.serial_prefix}
    if item is not None:
        current = SERIAL_RE.match(item.serial or "")
        if current:
            # An item keeps the prefix it was issued under, even if the template's
            # prefix has since changed.
            allowed_prefixes.add(current.group(2))
    if m.group(2) not in allowed_prefixes:
        raise DomainError(
            f"Serials of '{template.name}' use the prefix '{template.serial_prefix}' "
            f"(e.g. {example})"
        )
    ensure_unique(db, value, item)
    return value


def ensure_unique(db: Session, serial: str, item: Item | None = None) -> None:
    clash = (
        db.query(Item)
        .filter(Item.serial == serial, Item.id != (item.id if item and item.id else -1))
        .first()
    )
    if clash is not None:
        raise DomainError(
            f"Serial '{serial}' is already used by {clash.type.value} '{clash.name}'"
        )
