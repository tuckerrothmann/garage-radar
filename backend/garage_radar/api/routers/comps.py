"""
Comps router — GET /comps, GET /comps/clusters

/comps:         filterable list of completed sales
/comps/clusters: all pre-computed price bands (nightly refresh)
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from garage_radar.api.deps import DBSession
from garage_radar.api.schemas import CompClusterOut, CompOut, CompPage
from garage_radar.db.models import (
    BodyStyleEnum,
    Comp,
    CompCluster,
    SourceEnum,
    TransmissionEnum,
)

router = APIRouter(tags=["comps"])

_MAX_LIMIT = 200


@router.get("/comps", response_model=CompPage)
async def list_comps(
    session: DBSession,
    make: Optional[str] = Query(None, description="e.g. Porsche"),
    model: Optional[str] = Query(None, description="e.g. 911"),
    generation: Optional[str] = Query(None, description="e.g. G6, C3 — free text"),
    body_style: Optional[str] = Query(None),
    transmission: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    sale_date_after: Optional[date] = Query(None, description="ISO date, e.g. 2024-01-01"),
    sale_date_before: Optional[date] = Query(None),
    price_min: Optional[float] = Query(None, ge=0),
    price_max: Optional[float] = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> CompPage:
    """Return a paginated list of completed sales."""
    stmt = select(Comp)

    if make:
        stmt = stmt.where(Comp.make.ilike(f"%{make}%"))
    if model:
        stmt = stmt.where(Comp.model.ilike(f"%{model}%"))
    if generation:
        stmt = stmt.where(Comp.generation.ilike(f"%{generation}%"))
    if body_style:
        try:
            stmt = stmt.where(Comp.body_style == BodyStyleEnum(body_style))
        except ValueError:
            raise HTTPException(400, f"Invalid body_style '{body_style}'")
    if transmission:
        try:
            stmt = stmt.where(Comp.transmission == TransmissionEnum(transmission))
        except ValueError:
            raise HTTPException(400, f"Invalid transmission '{transmission}'")
    if source:
        try:
            stmt = stmt.where(Comp.source == SourceEnum(source))
        except ValueError:
            raise HTTPException(400, f"Invalid source '{source}'")
    if sale_date_after is not None:
        stmt = stmt.where(Comp.sale_date >= sale_date_after)
    if sale_date_before is not None:
        stmt = stmt.where(Comp.sale_date <= sale_date_before)
    if price_min is not None:
        stmt = stmt.where(Comp.sale_price >= price_min)
    if price_max is not None:
        stmt = stmt.where(Comp.sale_price <= price_max)

    total = (await session.scalar(select(func.count()).select_from(stmt.subquery()))) or 0
    stmt = stmt.order_by(Comp.sale_date.desc().nullslast(), Comp.created_at.desc())
    stmt = stmt.offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()

    return CompPage(
        total=total,
        limit=limit,
        offset=offset,
        items=[CompOut.model_validate(r) for r in rows],
    )


@router.get("/comps/clusters", response_model=list[CompClusterOut])
async def list_comp_clusters(
    session: DBSession,
    make: Optional[str] = Query(None, description="e.g. Porsche"),
    model: Optional[str] = Query(None, description="e.g. 911"),
    body_style: Optional[str] = Query(None),
    transmission: Optional[str] = Query(None),
    insufficient_data: Optional[bool] = Query(None),
) -> list[CompClusterOut]:
    """
    Return all pre-computed comp clusters.

    Optionally filter by make/model/body_style/transmission or
    insufficient_data=true to see only thin clusters.
    """
    stmt = select(CompCluster)

    if make:
        stmt = stmt.where(CompCluster.make.ilike(f"%{make}%"))
    if model:
        stmt = stmt.where(CompCluster.model.ilike(f"%{model}%"))
    if body_style:
        try:
            stmt = stmt.where(CompCluster.body_style == BodyStyleEnum(body_style))
        except ValueError:
            raise HTTPException(400, f"Invalid body_style '{body_style}'")
    if transmission:
        try:
            stmt = stmt.where(CompCluster.transmission == TransmissionEnum(transmission))
        except ValueError:
            raise HTTPException(400, f"Invalid transmission '{transmission}'")
    if insufficient_data is not None:
        stmt = stmt.where(CompCluster.insufficient_data == insufficient_data)

    stmt = stmt.order_by(CompCluster.cluster_key)
    rows = (await session.execute(stmt)).scalars().all()
    return [CompClusterOut.model_validate(r) for r in rows]
