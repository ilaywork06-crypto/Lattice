"""Locations — also feeds the map POC (§ implementation extras)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_editor, require_manager, require_viewer
from lattice_core.models import Item, Location, User
from lattice_core.schemas import LocationCreate, LocationOut

router = APIRouter(prefix="/locations", tags=["locations"])


def _serialize(db: Session, loc: Location) -> LocationOut:
    count = (
        db.query(func.count(Item.id)).filter(Item.location_id == loc.id).scalar() or 0
    )
    return LocationOut(
        id=loc.id,
        name=loc.name,
        building=loc.building,
        room=loc.room,
        x=loc.x,
        y=loc.y,
        notes=loc.notes,
        item_count=count,
    )


def _check_unique_name(db: Session, name: str, exclude_id: int | None = None) -> None:
    """Two locations with the same name are indistinguishable in every picker."""
    clash = (
        db.query(Location)
        .filter(func.lower(func.trim(Location.name)) == name.strip().lower())
        .filter(Location.id != (exclude_id or -1))
        .first()
    )
    if clash:
        raise HTTPException(
            status_code=400,
            detail=f"A location named '{clash.name}' already exists (#{clash.id})",
        )


@router.get("", response_model=list[LocationOut])
def list_locations(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return [_serialize(db, loc) for loc in db.query(Location).order_by(Location.name).all()]


@router.post("", response_model=LocationOut, status_code=201)
def create_location(
    data: LocationCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
):
    _check_unique_name(db, data.name)
    loc = Location(**data.model_dump())
    loc.name = loc.name.strip()
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return _serialize(db, loc)


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(
    location_id: int,
    data: LocationCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
):
    loc = db.get(Location, location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Location not found")
    _check_unique_name(db, data.name, exclude_id=location_id)
    for k, v in data.model_dump().items():
        setattr(loc, k, v)
    loc.name = loc.name.strip()
    db.commit()
    db.refresh(loc)
    return _serialize(db, loc)


@router.delete("/{location_id}", status_code=204)
def delete_location(
    location_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    loc = db.get(Location, location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Location not found")
    db.delete(loc)
    db.commit()
