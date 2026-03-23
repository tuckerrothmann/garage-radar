"""
GET/POST/DELETE /watchlist — manage the crawler watchlist.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from garage_radar.watchlist import get_watched_vehicles, save_watched_vehicles, WatchedVehicle

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchedVehicleOut(BaseModel):
    index: int
    make: str
    model: str
    year_min: int
    year_max: int
    search_override: dict[str, str] = {}


class WatchedVehicleIn(BaseModel):
    make: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=100)
    year_min: int = Field(..., ge=1900, le=2030)
    year_max: int = Field(..., ge=1900, le=2030)
    search_override: Optional[dict[str, str]] = None


@router.get("", response_model=list[WatchedVehicleOut])
async def list_watchlist():
    """Return the current watchlist."""
    vehicles = get_watched_vehicles()
    return [
        WatchedVehicleOut(index=i, **{
            "make": v.make,
            "model": v.model,
            "year_min": v.year_min,
            "year_max": v.year_max,
            "search_override": v.search_override,
        })
        for i, v in enumerate(vehicles)
    ]


@router.post("", response_model=WatchedVehicleOut, status_code=201)
async def add_to_watchlist(body: WatchedVehicleIn):
    """Add a vehicle to the watchlist."""
    if body.year_max < body.year_min:
        raise HTTPException(status_code=422, detail="year_max must be >= year_min")

    vehicles = get_watched_vehicles()
    new_vehicle = WatchedVehicle(
        make=body.make,
        model=body.model,
        year_min=body.year_min,
        year_max=body.year_max,
        search_override=body.search_override or {},
    )
    vehicles.append(new_vehicle)
    save_watched_vehicles(vehicles)
    return WatchedVehicleOut(
        index=len(vehicles) - 1,
        make=new_vehicle.make,
        model=new_vehicle.model,
        year_min=new_vehicle.year_min,
        year_max=new_vehicle.year_max,
        search_override=new_vehicle.search_override,
    )


@router.delete("/{index}", status_code=204)
async def remove_from_watchlist(index: int):
    """Remove a vehicle from the watchlist by index."""
    vehicles = get_watched_vehicles()
    if index < 0 or index >= len(vehicles):
        raise HTTPException(status_code=404, detail=f"No watchlist entry at index {index}")
    vehicles.pop(index)
    save_watched_vehicles(vehicles)
