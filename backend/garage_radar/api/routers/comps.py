"""
Comps router.

Supports repeated or comma-separated values for categorical filters.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from garage_radar.api.deps import DBSession
from garage_radar.api.filtering import parse_enum_values, parse_int_values, split_multi_values
from garage_radar.api.schemas import CompClusterOut, CompOut, CompPage
from garage_radar.db.models import (
    BodyStyleEnum,
    Comp,
    CompCluster,
    GenerationEnum,
    SourceEnum,
    TransmissionEnum,
)

router = APIRouter(tags=["comps"])

_MAX_LIMIT = 200


@router.get("/comps", response_model=CompPage)
async def list_comps(
    session: DBSession,
    make: list[str] | None = Query(None),
    model: list[str] | None = Query(None),
    generation: list[str] | None = Query(None, description="Repeated or comma-separated, e.g. G5,G6"),
    body_style: list[str] | None = Query(None),
    transmission: list[str] | None = Query(None),
    source: list[str] | None = Query(None),
    year: list[str] | None = Query(None, description="Exact years, repeated or comma-separated"),
    sale_date_after: date | None = Query(None, description="ISO date, e.g. 2024-01-01"),
    sale_date_before: date | None = Query(None),
    price_min: float | None = Query(None, ge=0),
    price_max: float | None = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> CompPage:
    """Return a paginated list of completed sales."""
    stmt = select(Comp)

    make_values = [value.lower() for value in split_multi_values(make)]
    model_values = [value.lower() for value in split_multi_values(model)]
    generation_values = parse_enum_values(GenerationEnum, generation, "generation")
    body_style_values = parse_enum_values(BodyStyleEnum, body_style, "body_style")
    transmission_values = parse_enum_values(TransmissionEnum, transmission, "transmission")
    source_values = parse_enum_values(SourceEnum, source, "source")
    year_values = parse_int_values(year, "year")

    if make_values:
        stmt = stmt.where(func.lower(Comp.make).in_(make_values))
    if model_values:
        stmt = stmt.where(func.lower(Comp.model).in_(model_values))
    if generation_values:
        stmt = stmt.where(Comp.generation.in_(generation_values))
    if body_style_values:
        stmt = stmt.where(Comp.body_style.in_(body_style_values))
    if transmission_values:
        stmt = stmt.where(Comp.transmission.in_(transmission_values))
    if source_values:
        stmt = stmt.where(Comp.source.in_(source_values))
    if year_values:
        stmt = stmt.where(Comp.year.in_(year_values))
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
        items=[CompOut.model_validate(row) for row in rows],
    )


@router.get("/comps/clusters", response_model=list[CompClusterOut])
async def list_comp_clusters(
    session: DBSession,
    make: list[str] | None = Query(None),
    model: list[str] | None = Query(None),
    generation: list[str] | None = Query(None),
    year_bucket: list[str] | None = Query(None, description="Exact years, repeated or comma-separated"),
    body_style: list[str] | None = Query(None),
    transmission: list[str] | None = Query(None),
    insufficient_data: bool | None = Query(None),
) -> list[CompClusterOut]:
    """Return all pre-computed comp clusters."""
    stmt = select(CompCluster)

    make_values = [value.lower() for value in split_multi_values(make)]
    model_values = [value.lower() for value in split_multi_values(model)]
    generation_values = parse_enum_values(GenerationEnum, generation, "generation")
    year_bucket_values = parse_int_values(year_bucket, "year_bucket")
    body_style_values = parse_enum_values(BodyStyleEnum, body_style, "body_style")
    transmission_values = parse_enum_values(TransmissionEnum, transmission, "transmission")

    if make_values:
        stmt = stmt.where(func.lower(CompCluster.make).in_(make_values))
    if model_values:
        stmt = stmt.where(func.lower(CompCluster.model).in_(model_values))
    if generation_values:
        stmt = stmt.where(CompCluster.generation.in_(generation_values))
    if year_bucket_values:
        stmt = stmt.where(CompCluster.year_bucket.in_(year_bucket_values))
    if body_style_values:
        stmt = stmt.where(CompCluster.body_style.in_(body_style_values))
    if transmission_values:
        stmt = stmt.where(CompCluster.transmission.in_(transmission_values))
    if insufficient_data is not None:
        stmt = stmt.where(CompCluster.insufficient_data == insufficient_data)

    stmt = stmt.order_by(CompCluster.cluster_key)
    rows = (await session.execute(stmt)).scalars().all()
    return [CompClusterOut.model_validate(row) for row in rows]
