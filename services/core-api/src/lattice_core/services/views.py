"""Read-side presenters: ORM rows → API shapes.

Ids are what the database stores; people read names. Everything here resolves a
stored value into something displayable (``display``) next to the raw value, so
the UI never has to fetch a catalog or a user list just to render one item.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from lattice_core.models import (
    CatalogOption,
    Document,
    FieldMode,
    FieldType,
    Item,
    ItemState,
    ItemTemplate,
    Location,
    TemplateField,
    User,
)
from lattice_core.schemas import (
    CatalogRef,
    CompositionRow,
    DocumentOut,
    ItemBrief,
    ItemFieldOut,
    ItemListOut,
    ItemOut,
    LocationOut,
    StateHistoryOut,
    TemplateBrief,
    TemplateChildOut,
    TemplateCounts,
    TemplateFieldOut,
    TemplateOut,
    TemplateSummary,
    UserBrief,
)
from lattice_core.services import fields as fields_svc
from lattice_core.services import items as items_svc
from lattice_core.services import serials as serials_svc


# ─────────────────────────── value display ───────────────────────────
def display_value(db: Session, field_type: FieldType, value):  # noqa: C901
    if fields_svc.is_empty(value):
        return None
    if field_type in (FieldType.industry, FieldType.project, FieldType.team):
        option = db.get(CatalogOption, value)
        return option.value if option else f"#{value}"
    if field_type == FieldType.managers:
        users = {u.id: u for u in db.query(User).filter(User.id.in_(value)).all()}
        return [users[i].full_name if i in users else f"#{i}" for i in value]
    if field_type == FieldType.responsible:
        user = db.get(User, value)
        return user.full_name if user else f"#{value}"
    if field_type == FieldType.location:
        loc = db.get(Location, value)
        return loc.name if loc else f"#{value}"
    if field_type == FieldType.parent:
        item = db.get(Item, value)
        return item.label if item else f"#{value}"
    if field_type == FieldType.files:
        docs = db.query(Document).filter(Document.id.in_(value)).all()
        order = {d: i for i, d in enumerate(value)}
        docs.sort(key=lambda d: order.get(d.id, 0))
        return [DocumentOut.model_validate(d).model_dump(mode="json") for d in docs]
    return value


def options_display(db: Session, field: TemplateField) -> list[str]:
    options = (field.config or {}).get("options") or []
    if field.field_type == FieldType.enum or field.mode != FieldMode.choice:
        return [str(o) for o in options]
    out = []
    for o in options:
        raw = [o] if field.field_type == FieldType.managers else o
        d = display_value(db, field.field_type, raw)
        out.append(d[0] if isinstance(d, list) else str(d))
    return out


# ─────────────────────────── templates ───────────────────────────
def template_counts(
    db: Session, template_ids: list[int] | None = None
) -> dict[int, TemplateCounts]:
    q = db.query(Item.template_id, Item.state, func.coalesce(func.sum(Item.quantity), 0))
    if template_ids is not None:
        q = q.filter(Item.template_id.in_(template_ids))
    out: dict[int, TemplateCounts] = defaultdict(TemplateCounts)
    for tid, state, units in q.group_by(Item.template_id, Item.state).all():
        c = out[tid]
        units = int(units or 0)
        if state == ItemState.destroyed:
            c.destroyed += units
            continue
        setattr(c, state.value, getattr(c, state.value) + units)
        c.total += units
    return out


def template_brief(t: ItemTemplate) -> TemplateBrief:
    return TemplateBrief(
        id=t.id, type=t.type, name=t.name, card_type=t.card_type, serial_prefix=t.serial_prefix
    )


def template_summary(t: ItemTemplate, counts: TemplateCounts | None = None) -> TemplateSummary:
    return TemplateSummary(
        **template_brief(t).model_dump(),
        tracking=t.tracking,
        description=t.description,
        counts=counts or TemplateCounts(),
        child_template_ids=[c.id for c in t.child_templates],
        parent_template_ids=[p.id for p in t.parent_templates],
        field_count=len(t.fields),
        updated_at=t.updated_at,
    )


def template_out(db: Session, t: ItemTemplate) -> TemplateOut:
    counts = template_counts(db, [t.id]).get(t.id)
    template_docs: dict[int, list[Document]] = defaultdict(list)
    for d in db.query(Document).filter(Document.template_id == t.id).all():
        if d.field_id is not None:
            template_docs[d.field_id].append(d)
    fields = []
    for f in t.fields:
        fields.append(TemplateFieldOut(
            id=f.id, key=f.key, label=f.label, field_type=f.field_type, mode=f.mode,
            required=f.required, position=f.position, config=f.config or {},
            fixed_value=f.fixed_value,
            fixed_display=display_value(db, f.field_type, f.fixed_value),
            options_display=options_display(db, f),
            files=[DocumentOut.model_validate(d) for d in template_docs.get(f.id, [])],
        ))
    return TemplateOut(
        **template_summary(t, counts).model_dump(),
        fields=fields,
        child_templates=[template_brief(c) for c in t.child_templates],
        parent_templates=[template_brief(p) for p in t.parent_templates],
        children=[
            TemplateChildOut(
                template=template_brief(link.child),
                min_count=link.min_count,
                max_count=link.max_count,
            )
            for link in t.child_links
        ],
        next_serial=serials_svc.next_serial(db, t),
        created_at=t.created_at,
    )


# ─────────────────────────── items ───────────────────────────
def item_brief(i: Item) -> ItemBrief:
    return ItemBrief(
        id=i.id, type=i.type, template_id=i.template_id, name=i.name, serial=i.serial,
        state=i.state, card_type=i.card_type, location_id=i.location_id,
    )


def _catalog_ref(option: CatalogOption | None) -> CatalogRef | None:
    return CatalogRef(id=option.id, value=option.value) if option else None


def _location_out(loc: Location | None) -> LocationOut | None:
    if loc is None:
        return None
    return LocationOut(
        id=loc.id, name=loc.name, building=loc.building, room=loc.room, x=loc.x, y=loc.y,
        notes=loc.notes, is_desiccator=loc.is_desiccator,
    )


def item_fields(db: Session, item: Item) -> list[ItemFieldOut]:
    out = []
    for f in item.template.fields:
        value = items_svc.effective_value(db, item, f)
        out.append(ItemFieldOut(
            field_id=f.id, key=f.key, label=f.label, field_type=f.field_type, mode=f.mode,
            required=f.required, config=f.config or {}, value=value,
            display=display_value(db, f.field_type, value),
            missing=f.required and fields_svc.is_empty(value),
        ))
    return out


def item_out(db: Session, item: Item) -> ItemOut:
    t = item.template
    general_docs = [d for d in item.documents if d.field_id is None]
    composition = [
        CompositionRow(**{**row, "template": template_brief(row["template"])})
        for row in items_svc.composition(item)
    ]
    return ItemOut(
        id=item.id,
        type=item.type,
        template=template_brief(t),
        name=item.name,
        serial=item.serial,
        state=item.state,
        card_type=item.card_type,
        tracking=t.tracking,
        quantity=item.quantity,
        storage_status=item.storage_status,
        parent_id=item.parent_id,
        location_id=item.location_id,
        location=_location_out(item.location),
        parent=item_brief(item.parent) if item.parent else None,
        children=[item_brief(c) for c in item.children],
        industry=_catalog_ref(item.industry),
        project=_catalog_ref(item.project),
        team=_catalog_ref(item.team),
        responsible=UserBrief.model_validate(item.responsible) if item.responsible else None,
        managers=[UserBrief.model_validate(m) for m in item.managers],
        fields=item_fields(db, item),
        state_history=[StateHistoryOut.model_validate(h) for h in item.state_history],
        documents=[DocumentOut.model_validate(d) for d in general_docs],
        extra_items=list(item.extra_items),
        child_templates=[template_brief(c) for c in t.child_templates],
        parent_templates=[template_brief(p) for p in t.parent_templates],
        composition=composition,
        is_complete=not any(row.missing for row in composition),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def item_list_out(i: Item) -> ItemListOut:
    return ItemListOut(
        id=i.id,
        type=i.type,
        template_id=i.template_id,
        name=i.name,
        serial=i.serial,
        state=i.state,
        card_type=i.card_type,
        quantity=i.quantity,
        storage_status=i.storage_status,
        parent_id=i.parent_id,
        parent_label=i.parent.label if i.parent else None,
        location_id=i.location_id,
        location_name=i.location.name if i.location else None,
        industry=i.industry.value if i.industry else None,
        project=i.project.value if i.project else None,
        team=i.team.value if i.team else None,
        children_count=len(i.children),
        missing_children=items_svc.missing_children(i),
        manager_names=[m.full_name for m in i.managers],
        updated_at=i.updated_at,
    )
