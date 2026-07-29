"""Hierarchy graph feed for the frontend visualization."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_viewer
from lattice_core.models import Item, User
from lattice_core.schemas import GraphEdge, GraphNode, GraphOut

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("", response_model=GraphOut)
def hierarchy(
    root_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    """Full parent→child hierarchy, or the subtree under ``root_id``."""
    items = db.query(Item).filter(Item.is_template.is_(False)).all()
    by_id = {i.id: i for i in items}

    selected: set[int]
    if root_id is not None and root_id in by_id:
        selected = set()
        stack = [root_id]
        while stack:
            cur = stack.pop()
            if cur in selected:
                continue
            selected.add(cur)
            stack.extend(c.id for c in by_id[cur].children)
    else:
        selected = set(by_id)

    nodes = [
        GraphNode(
            id=i.id,
            label=i.name,
            type=i.type,
            state=i.state,
            card_type=i.card_type,
        )
        for i in items
        if i.id in selected
    ]
    edges = [
        GraphEdge(source=i.parent_id, target=i.id)
        for i in items
        if i.parent_id in selected and i.id in selected
    ]
    return GraphOut(nodes=nodes, edges=edges)
