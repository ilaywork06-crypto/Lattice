"""Admin-managed catalogs: project, industry and team vocabularies, and the
two-way links between them.

Everyone can read the options (to populate dropdowns); only managers may add,
edit, link or remove them.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_manager, require_viewer
from lattice_core.models import CatalogCategory, CatalogOption, User
from lattice_core.schemas import (
    CatalogLinkOut,
    CatalogLinksUpdate,
    CatalogOptionCreate,
    CatalogOptionOut,
    CatalogOptionUpdate,
)
from lattice_core.services import catalog as svc

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _to_out(db: Session, option: CatalogOption, links: dict[int, list[int]] | None = None):
    return CatalogOptionOut(
        id=option.id,
        category=option.category,
        value=option.value,
        description=option.description,
        active=option.active,
        sort_order=option.sort_order,
        usage_count=svc.usage_count(db, option),
        linked_ids=(links or {}).get(option.id, []) if links is not None
        else svc.linked_ids(db, option.id),
    )


def _get(db: Session, option_id: int) -> CatalogOption:
    option = db.get(CatalogOption, option_id)
    if option is None:
        raise HTTPException(status_code=404, detail="Catalog option not found")
    return option


@router.get("", response_model=list[CatalogOptionOut])
def list_options(
    category: CatalogCategory | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    links: dict[int, list[int]] = {}
    for a, b in svc.all_links(db):
        links.setdefault(a, []).append(b)
        links.setdefault(b, []).append(a)
    return [_to_out(db, o, links) for o in svc.list_options(db, category, active_only)]


@router.get("/links", response_model=list[CatalogLinkOut])
def list_links(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return [CatalogLinkOut(a_id=a, b_id=b) for a, b in svc.all_links(db)]


@router.post("", response_model=CatalogOptionOut, status_code=201)
def create_option(
    body: CatalogOptionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    option = svc.create_option(db, body.model_dump())
    db.commit()
    return _to_out(db, option)


@router.patch("/{option_id}", response_model=CatalogOptionOut)
def update_option(
    option_id: int,
    body: CatalogOptionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    option = _get(db, option_id)
    svc.update_option(db, option, body.model_dump(exclude_unset=True))
    db.commit()
    return _to_out(db, option)


@router.put("/{option_id}/links", response_model=CatalogOptionOut)
def set_links(
    option_id: int,
    body: CatalogLinksUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    """Set this value's links to one other category (e.g. a team's industries).

    Links are two-way: the industries of a team and the teams of an industry
    are the same rows, so editing either end updates both.
    """
    option = _get(db, option_id)
    svc.set_links(db, option, body.category, body.option_ids)
    db.commit()
    return _to_out(db, option)


@router.delete("/{option_id}", status_code=204)
def delete_option(
    option_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    svc.delete_option(db, _get(db, option_id))
    db.commit()
