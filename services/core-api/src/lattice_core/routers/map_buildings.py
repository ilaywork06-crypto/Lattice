"""Editable floor-plan background: buildings/zones drawn behind the markers.

Everyone can read them (to render the map); editors+ can add/edit and managers
can delete — mirroring how locations are governed.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from lattice_core.database import get_db
from lattice_core.deps import require_editor, require_manager, require_viewer
from lattice_core.models import MapBuilding, User
from lattice_core.schemas import MapBuildingCreate, MapBuildingOut, MapBuildingUpdate

router = APIRouter(prefix="/map", tags=["map"])


@router.get("/buildings", response_model=list[MapBuildingOut])
def list_buildings(db: Session = Depends(get_db), _: User = Depends(require_viewer)):
    return (
        db.query(MapBuilding)
        .order_by(MapBuilding.sort_order, MapBuilding.id)
        .all()
    )


@router.post("/buildings", response_model=MapBuildingOut, status_code=201)
def create_building(
    data: MapBuildingCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
):
    building = MapBuilding(**data.model_dump())
    db.add(building)
    db.commit()
    db.refresh(building)
    return building


@router.patch("/buildings/{building_id}", response_model=MapBuildingOut)
def update_building(
    building_id: int,
    data: MapBuildingUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_editor),
):
    building = db.get(MapBuilding, building_id)
    if building is None:
        raise HTTPException(status_code=404, detail="Building not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(building, k, v)
    db.commit()
    db.refresh(building)
    return building


@router.delete("/buildings/{building_id}", status_code=204)
def delete_building(
    building_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_manager),
):
    building = db.get(MapBuilding, building_id)
    if building is None:
        raise HTTPException(status_code=404, detail="Building not found")
    db.delete(building)
    db.commit()
