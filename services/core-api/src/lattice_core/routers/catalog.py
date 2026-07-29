"""Admin-managed catalogs: project & industry vocabularies (requirement §2).

Everyone can read the options (to populate dropdowns); only managers (admins)
may add, edit or remove them.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_manager, require_viewer
from lattice_core.models import CatalogCategory, CatalogOption, User
from lattice_core.schemas import (
    CatalogOptionCreate,
    CatalogOptionOut,
    CatalogOptionUpdate,
)
from lattice_core.services import catalog as svc

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _to_out(db: Session, option: CatalogOption) -> CatalogOptionOut:
    return CatalogOptionOut(
        id=option.id,
        category=option.category,
        value=option.value,
        description=option.description,
        active=option.active,
        sort_order=option.sort_order,
        usage_count=svc.usage_count(db, option),
    )


@router.get("", response_model=list[CatalogOptionOut])
def list_options(
    category: CatalogCategory | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_viewer),
):
    return [_to_out(db, o) for o in svc.list_options(db, category, active_only)]


@router.post("", response_model=CatalogOptionOut, status_code=201)
def create_option(
    body: CatalogOptionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    try:
        option = svc.create_option(db, body.model_dump())
    except svc.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return _to_out(db, option)


@router.patch("/{option_id}", response_model=CatalogOptionOut)
def update_option(
    option_id: int,
    body: CatalogOptionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    option = db.get(CatalogOption, option_id)
    if option is None:
        raise HTTPException(status_code=404, detail="Catalog option not found")
    try:
        svc.update_option(db, option, body.model_dump(exclude_unset=True))
    except svc.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return _to_out(db, option)


@router.delete("/{option_id}", status_code=204)
def delete_option(
    option_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    option = db.get(CatalogOption, option_id)
    if option is None:
        raise HTTPException(status_code=404, detail="Catalog option not found")
    try:
        svc.delete_option(db, option)
    except svc.CatalogError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
