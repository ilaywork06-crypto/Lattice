"""Admin-managed controlled vocabularies: projects, industries and teams.

Items reference a value **by id**, so renaming a value is a single row and every
item follows; a value still in use (by an item or by a template's field) cannot
be deleted — deactivate it instead.

Any two values of *different* categories can be linked (team ↔ industry,
team ↔ project, industry ↔ project), many-to-many and in both directions. A link
is one row in ``catalog_links`` with the smaller id first, so it reads the same
from either end.
"""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from lattice_core.errors import DomainError
from lattice_core.models import (
    CATALOG_FIELD_TYPES,
    CatalogCategory,
    CatalogLink,
    CatalogOption,
    FieldMode,
    Item,
    TemplateField,
)

_ITEM_COLUMN = {
    CatalogCategory.industry: Item.industry_id,
    CatalogCategory.project: Item.project_id,
    CatalogCategory.team: Item.team_id,
}
_FIELD_TYPE_FOR = {category: ft for ft, category in CATALOG_FIELD_TYPES.items()}


class CatalogError(DomainError):
    """Raised on an invalid catalog operation (mapped to HTTP 400)."""


def list_options(
    db: Session,
    category: CatalogCategory | None = None,
    active_only: bool = False,
) -> list[CatalogOption]:
    q = db.query(CatalogOption)
    if category is not None:
        q = q.filter(CatalogOption.category == category)
    if active_only:
        q = q.filter(CatalogOption.active.is_(True))
    return q.order_by(
        CatalogOption.category, CatalogOption.sort_order, CatalogOption.value
    ).all()


def usage_count(db: Session, option: CatalogOption) -> int:
    """How many items reference this value."""
    column = _ITEM_COLUMN[option.category]
    return db.query(func.count(Item.id)).filter(column == option.id).scalar() or 0


def template_usage(db: Session, option: CatalogOption) -> list[str]:
    """Names of templates whose fields fix or list this value."""
    field_type = _FIELD_TYPE_FOR[option.category]
    names = []
    for f in db.query(TemplateField).filter(TemplateField.field_type == field_type).all():
        listed = option.id in ((f.config or {}).get("options") or [])
        fixed = f.mode == FieldMode.fixed and f.fixed_value == option.id
        if listed or fixed:
            names.append(f.template.name)
    return sorted(set(names))


def create_option(db: Session, data: dict) -> CatalogOption:
    category = data["category"]
    value = data["value"].strip()
    if not value:
        raise CatalogError("Value cannot be empty")
    exists = (
        db.query(CatalogOption)
        .filter(CatalogOption.category == category, CatalogOption.value == value)
        .first()
    )
    if exists is not None:
        raise CatalogError(f"'{value}' already exists in {category.value}s")
    option = CatalogOption(
        category=category,
        value=value,
        description=data.get("description"),
        active=data.get("active", True),
        sort_order=data.get("sort_order", 0),
    )
    db.add(option)
    db.flush()
    return option


def update_option(db: Session, option: CatalogOption, data: dict) -> CatalogOption:
    new_value = data.get("value")
    if new_value is not None:
        new_value = new_value.strip()
        if not new_value:
            raise CatalogError("Value cannot be empty")
        if new_value != option.value:
            clash = (
                db.query(CatalogOption)
                .filter(
                    CatalogOption.category == option.category,
                    CatalogOption.value == new_value,
                    CatalogOption.id != option.id,
                )
                .first()
            )
            if clash is not None:
                raise CatalogError(f"'{new_value}' already exists")
            # Items hold the id, so a rename needs no cascade.
            option.value = new_value
    for attr in ("description", "active", "sort_order"):
        if attr in data and data[attr] is not None:
            setattr(option, attr, data[attr])
    return option


def delete_option(db: Session, option: CatalogOption) -> None:
    if usage_count(db, option) > 0:
        raise CatalogError(
            "This value is in use by existing items; deactivate it instead of deleting."
        )
    templates = template_usage(db, option)
    if templates:
        raise CatalogError(
            "This value is used by the template(s) "
            + ", ".join(f"'{n}'" for n in templates)
            + "; remove it there first or deactivate it instead."
        )
    from lattice_core.services.field_groups import forget_reference

    forget_reference(db, {_FIELD_TYPE_FOR[option.category]}, option.id)
    db.delete(option)


# ─────────────────────────── links ───────────────────────────
def _pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def linked_ids(db: Session, option_id: int) -> list[int]:
    rows = (
        db.query(CatalogLink)
        .filter(or_(CatalogLink.option_a_id == option_id, CatalogLink.option_b_id == option_id))
        .all()
    )
    return [r.option_b_id if r.option_a_id == option_id else r.option_a_id for r in rows]


def all_links(db: Session) -> list[tuple[int, int]]:
    return [(r.option_a_id, r.option_b_id) for r in db.query(CatalogLink).all()]


def set_links(
    db: Session,
    option: CatalogOption,
    category: CatalogCategory,
    target_ids: list[int],
) -> list[int]:
    """Make ``option``'s links to values of ``category`` exactly ``target_ids``.

    Scoped to one category at a time, so editing a team's projects never touches
    its industries. Both ends see the result: it is the same row.
    """
    if category == option.category:
        raise CatalogError("A value can only be linked to values of another category")
    wanted = list(dict.fromkeys(target_ids))
    targets = (
        db.query(CatalogOption).filter(CatalogOption.id.in_(wanted)).all() if wanted else []
    )
    if len(targets) != len(wanted):
        raise CatalogError("One or more values to link no longer exist")
    for t in targets:
        if t.category != category:
            raise CatalogError(f"'{t.value}' is a {t.category.value}, not a {category.value}")

    current = {
        oid
        for oid in linked_ids(db, option.id)
        if db.get(CatalogOption, oid).category == category
    }
    for oid in current - set(wanted):
        a, b = _pair(option.id, oid)
        db.query(CatalogLink).filter(
            CatalogLink.option_a_id == a, CatalogLink.option_b_id == b
        ).delete(synchronize_session=False)
    for oid in set(wanted) - current:
        a, b = _pair(option.id, oid)
        db.add(CatalogLink(option_a_id=a, option_b_id=b))
    db.flush()
    return wanted


def link(db: Session, a_id: int, b_id: int) -> None:
    a, b = db.get(CatalogOption, a_id), db.get(CatalogOption, b_id)
    if a is None or b is None:
        raise CatalogError("Catalog value not found")
    if a.category == b.category:
        raise CatalogError("A value can only be linked to values of another category")
    lo, hi = _pair(a_id, b_id)
    exists = db.get(CatalogLink, (lo, hi))
    if exists is None:
        db.add(CatalogLink(option_a_id=lo, option_b_id=hi))
        db.flush()
