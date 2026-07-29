"""Admin-managed controlled vocabularies (requirement §2).

Projects and industries are no longer free text: an admin defines the allowed
values here, and items may only reference an *active* value from the list. This
keeps the data clean and consistent as the system scales to many users.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from lattice_core.models import CatalogCategory, CatalogOption, Item

# Which item column each catalog category controls.
_CATEGORY_FIELD: dict[CatalogCategory, str] = {
    CatalogCategory.project: "project",
    CatalogCategory.industry: "industry",
}


class CatalogError(ValueError):
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
    """How many (non-template) items currently reference this value."""
    field = getattr(Item, _CATEGORY_FIELD[option.category])
    return (
        db.query(func.count(Item.id))
        .filter(field == option.value, Item.is_template.is_(False))
        .scalar()
        or 0
    )


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
            # keep existing items in sync with the renamed value
            field = _CATEGORY_FIELD[option.category]
            db.query(Item).filter(getattr(Item, field) == option.value).update(
                {field: new_value}, synchronize_session=False
            )
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
    db.delete(option)


def allowed_values(db: Session, category: CatalogCategory) -> set[str]:
    return {
        o.value
        for o in db.query(CatalogOption).filter(
            CatalogOption.category == category, CatalogOption.active.is_(True)
        )
    }


def validate_item_catalog(db: Session, project: str | None, industry: str | None) -> None:
    """Ensure project/industry (when provided) reference an active catalog value."""
    if project:
        if project not in allowed_values(db, CatalogCategory.project):
            raise CatalogError(
                f"'{project}' is not a known project. Ask an admin to add it in Catalog."
            )
    if industry:
        if industry not in allowed_values(db, CatalogCategory.industry):
            raise CatalogError(
                f"'{industry}' is not a known industry. Ask an admin to add it in Catalog."
            )
