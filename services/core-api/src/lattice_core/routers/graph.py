"""Hierarchy graphs for the frontend visualisation.

Drawing every item in one picture stops being readable long before the system
stops growing, so there are three focused views instead:

* ``/graph/templates`` — the hierarchy as the *templates* define it (which
  kinds of setup hold which assemblies and cards). Small, stable, always
  readable. ``root_template_id`` narrows it to one template's subtree.
* ``/graph?template_id=…`` — every live tree built from a chosen setup or
  assembly template (one tree per item of that template).
* ``/graph?root_id=…`` — one item's tree; ``ancestors=true`` adds the path up to
  the top so the item is shown in context (used on the item page).
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from lattice_core.database import get_db
from lattice_core.deps import require_viewer
from lattice_core.models import Item, ItemTemplate, User
from lattice_core.schemas import GraphEdge, GraphNode, GraphOut
from lattice_core.services import views

router = APIRouter(prefix="/graph", tags=["graph"])


def _subtree(item: Item) -> list[Item]:
    out: list[Item] = []
    seen: set[int] = set()
    stack = [item]
    while stack:
        cur = stack.pop()
        if cur.id in seen:
            continue
        seen.add(cur.id)
        out.append(cur)
        stack.extend(cur.children)
    return out


def _item_graph(items: list[Item], roots: list[int]) -> GraphOut:
    ids = {i.id for i in items}
    nodes = [
        GraphNode(
            id=i.id, label=i.name, type=i.type, state=i.state, card_type=i.card_type,
            serial=i.serial, template_id=i.template_id,
        )
        for i in items
    ]
    edges = [
        GraphEdge(source=i.parent_id, target=i.id)
        for i in items
        if i.parent_id in ids
    ]
    return GraphOut(nodes=nodes, edges=edges, roots=roots)


@router.get("", response_model=GraphOut)
def hierarchy(
    root_id: int | None = None,
    template_id: int | None = None,
    ancestors: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    if root_id is not None:
        root = db.get(Item, root_id)
        if root is None:
            raise HTTPException(status_code=404, detail="Item not found")
        items = _subtree(root)
        top = root
        if ancestors:
            cur = root.parent
            while cur is not None and cur not in items:
                items.append(cur)
                top = cur
                cur = cur.parent
        return _item_graph(items, [top.id])

    if template_id is not None:
        tpl = db.get(ItemTemplate, template_id)
        if tpl is None:
            raise HTTPException(status_code=404, detail="Template not found")
        roots = (
            db.query(Item)
            .options(joinedload(Item.template))
            .filter(Item.template_id == template_id)
            .order_by(Item.serial)
            .all()
        )
        items: list[Item] = []
        seen: set[int] = set()
        for r in roots:
            for i in _subtree(r):
                if i.id not in seen:
                    seen.add(i.id)
                    items.append(i)
        return _item_graph(items, [r.id for r in roots])

    # Everything — kept for small systems and scripts; the UI uses the views above.
    items = db.query(Item).options(joinedload(Item.template)).all()
    return _item_graph(items, [i.id for i in items if i.parent_id is None])


@router.get("/templates", response_model=GraphOut)
def template_hierarchy(
    root_template_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    templates = db.query(ItemTemplate).all()
    if root_template_id is not None:
        root = db.get(ItemTemplate, root_template_id)
        if root is None:
            raise HTTPException(status_code=404, detail="Template not found")
        selected: dict[int, ItemTemplate] = {}
        stack = [root]
        while stack:
            cur = stack.pop()
            if cur.id in selected:
                continue
            selected[cur.id] = cur
            stack.extend(cur.child_templates)
        templates = list(selected.values())
    counts = views.template_counts(db, [t.id for t in templates])
    ids = {t.id for t in templates}
    nodes = [
        GraphNode(
            id=t.id, label=t.name, type=t.type, card_type=t.card_type,
            serial=t.serial_prefix, template_id=t.id,
            count=counts[t.id].total if t.id in counts else 0,
        )
        for t in templates
    ]
    edges = [
        GraphEdge(source=t.id, target=c.id)
        for t in templates
        for c in t.child_templates
        if c.id in ids
    ]
    roots = [t.id for t in templates if not any(p.id in ids for p in t.parent_templates)]
    return GraphOut(nodes=nodes, edges=edges, roots=roots)
