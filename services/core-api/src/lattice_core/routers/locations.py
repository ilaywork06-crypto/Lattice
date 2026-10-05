"""Locations — also feed the floor-plan map and define the desiccator group."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_editor, require_manager, require_viewer
from lattice_core.models import Item, Location, TemplateField, User
from lattice_core.schemas import (
    DesiccatorUpdate,
    LocationCreate,
    LocationOut,
    LocationUpdate,
)
from lattice_core.services.audit import record_audit

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
        is_desiccator=loc.is_desiccator,
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
    user: User = Depends(require_editor),
):
    _check_unique_name(db, data.name)
    if data.is_desiccator and user.role.value != "manager":
        raise HTTPException(status_code=403, detail="Only managers define the desiccator")
    loc = Location(**data.model_dump())
    loc.name = loc.name.strip()
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return _serialize(db, loc)


@router.put("/desiccator", response_model=list[LocationOut])
def set_desiccator(
    body: DesiccatorUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager),
):
    """Define which locations make up the desiccator (the full set)."""
    wanted = set(body.location_ids)
    locations = db.query(Location).all()
    known = {loc.id for loc in locations}
    missing = wanted - known
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown locations: {sorted(missing)}")
    before = sorted(loc.id for loc in locations if loc.is_desiccator)
    for loc in locations:
        loc.is_desiccator = loc.id in wanted
    if before != sorted(wanted):
        record_audit(
            db,
            action="desiccator.update",
            summary=f"Desiccator now has {len(wanted)} location(s)",
            user=user,
            details={"before": before, "after": sorted(wanted)},
        )
    db.commit()
    return [_serialize(db, loc) for loc in sorted(locations, key=lambda x: x.name)]


@router.patch("/{location_id}", response_model=LocationOut)
def update_location(
    location_id: int,
    data: LocationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_editor),
):
    loc = db.get(Location, location_id)
    if loc is None:
        raise HTTPException(status_code=404, detail="Location not found")
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        _check_unique_name(db, changes["name"], exclude_id=location_id)
        changes["name"] = changes["name"].strip()
    if "is_desiccator" in changes and changes["is_desiccator"] != loc.is_desiccator:
        if user.role.value != "manager":
            raise HTTPException(status_code=403, detail="Only managers define the desiccator")
    for k, v in changes.items():
        if k in ("name", "x", "y", "is_desiccator") and v is None:
            continue
        setattr(loc, k, v)
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
    count = db.query(func.count(Item.id)).filter(Item.location_id == loc.id).scalar() or 0
    if count:
        raise HTTPException(
            status_code=400,
            detail=f"{count} item(s) are at '{loc.name}'; move them before deleting it",
        )
    # Template list fields may offer this location; drop it from their lists.
    for f in db.query(TemplateField).all():
        options = (f.config or {}).get("options")
        if f.field_type.value == "location" and options and loc.id in options:
            f.config = {**f.config, "options": [o for o in options if o != loc.id]}
    db.delete(loc)
    db.commit()
