"""
Vehicle profile router.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from garage_radar.api.deps import DBSession
from garage_radar.api.schemas import VehicleProfileOut
from garage_radar.vehicle_profiles import build_vehicle_profile

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("/profile", response_model=VehicleProfileOut)
async def get_vehicle_profile(
    session: DBSession,
    make: str = Query(..., min_length=1),
    model: str = Query(..., min_length=1),
    year: int | None = Query(None, ge=1886, le=2100),
    currency: str | None = Query(None, min_length=3, max_length=3),
) -> VehicleProfileOut:
    if not make.strip():
        raise HTTPException(400, "make is required")
    if not model.strip():
        raise HTTPException(400, "model is required")

    profile = await build_vehicle_profile(
        session,
        make=make,
        model=model,
        year=year,
        currency=currency,
    )
    return VehicleProfileOut.model_validate(profile)
