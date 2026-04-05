"""
Listings router.

Supports repeated or comma-separated values for categorical filters so the
UI can express multi-select searches without special backend endpoints.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.orm import selectinload

from garage_radar.api.deps import DBSession
from garage_radar.api.filtering import parse_enum_values, parse_int_values, split_multi_values
from garage_radar.api.schemas import ListingDetailOut, ListingOut, ListingPage
from garage_radar.db.models import (
    AlertStatusEnum,
    BodyStyleEnum,
    CompCluster,
    GenerationEnum,
    Listing,
    ListingStatusEnum,
    SourceEnum,
    TransmissionEnum,
)

router = APIRouter(prefix="/listings", tags=["listings"])

_MAX_LIMIT = 200


@router.get("", response_model=ListingPage)
async def list_listings(
    session: DBSession,
    make: list[str] | None = Query(None),  # noqa: B008
    model: list[str] | None = Query(None),  # noqa: B008
    generation: list[str] | None = Query(  # noqa: B008
        None,
        description="Repeated or comma-separated, e.g. G5,G6",
    ),
    body_style: list[str] | None = Query(None),  # noqa: B008
    transmission: list[str] | None = Query(None),  # noqa: B008
    status: list[str] | None = Query(["active"]),  # noqa: B008
    source: list[str] | None = Query(None),  # noqa: B008
    year: list[str] | None = Query(  # noqa: B008
        None,
        description="Exact years, repeated or comma-separated",
    ),
    year_min: int | None = Query(None, ge=1886, le=2100),  # noqa: B008
    year_max: int | None = Query(None, ge=1886, le=2100),  # noqa: B008
    price_min: float | None = Query(None, ge=0),  # noqa: B008
    price_max: float | None = Query(None, ge=0),  # noqa: B008
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),  # noqa: B008
    offset: int = Query(0, ge=0),  # noqa: B008
) -> ListingPage:
    """Return a paginated, filtered listing of vehicles."""
    stmt = select(Listing)

    make_values = [value.lower() for value in split_multi_values(make)]
    model_values = [value.lower() for value in split_multi_values(model)]
    status_values = parse_enum_values(ListingStatusEnum, status, "status")
    generation_values = parse_enum_values(GenerationEnum, generation, "generation")
    body_style_values = parse_enum_values(BodyStyleEnum, body_style, "body_style")
    transmission_values = parse_enum_values(TransmissionEnum, transmission, "transmission")
    source_values = parse_enum_values(SourceEnum, source, "source")
    year_values = parse_int_values(year, "year")

    if make_values:
        stmt = stmt.where(func.lower(Listing.make).in_(make_values))
    if model_values:
        stmt = stmt.where(func.lower(Listing.model).in_(model_values))
    if status_values:
        stmt = stmt.where(Listing.listing_status.in_(status_values))
    if generation_values:
        stmt = stmt.where(Listing.generation.in_(generation_values))
    if body_style_values:
        stmt = stmt.where(Listing.body_style.in_(body_style_values))
    if transmission_values:
        stmt = stmt.where(Listing.transmission.in_(transmission_values))
    if source_values:
        stmt = stmt.where(Listing.source.in_(source_values))
    if year_values:
        stmt = stmt.where(Listing.year.in_(year_values))
    if year_min is not None:
        stmt = stmt.where(Listing.year >= year_min)
    if year_max is not None:
        stmt = stmt.where(Listing.year <= year_max)
    effective_price = func.coalesce(Listing.current_bid, Listing.asking_price)
    if price_min is not None:
        stmt = stmt.where(effective_price >= price_min)
    if price_max is not None:
        stmt = stmt.where(effective_price <= price_max)

    total = (await session.scalar(select(func.count()).select_from(stmt.subquery()))) or 0

    stmt = stmt.order_by(Listing.created_at.desc()).offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    clusters = await _clusters_for(session, rows)
    items = [_enrich(row, clusters.get(_listing_cluster_key(row))) for row in rows]

    return ListingPage(total=total, limit=limit, offset=offset, items=items)


@router.get("/{listing_id}", response_model=ListingDetailOut)
async def get_listing(listing_id: uuid.UUID, session: DBSession) -> ListingDetailOut:
    """Return a single listing with price history and open alerts."""
    row = await session.scalar(
        select(Listing).where(Listing.id == listing_id).options(selectinload(Listing.alerts))
    )
    if row is None:
        raise HTTPException(404, "Listing not found")

    cluster = await _cluster_for(session, row)
    base = _enrich(row, cluster)
    open_alerts = [alert for alert in row.alerts if alert.status != AlertStatusEnum.dismissed]

    return ListingDetailOut(
        **base.model_dump(),
        price_history=row.price_history,
        alerts=open_alerts,
    )


async def _cluster_for(session, listing: Listing) -> CompCluster | None:
    """Fetch the matching comp cluster for a listing, if it exists."""
    if not (listing.make and listing.model and listing.body_style and listing.transmission):
        return None

    stmt = select(CompCluster).where(
        func.lower(CompCluster.make) == listing.make.strip().lower(),
        func.lower(CompCluster.model) == listing.model.strip().lower(),
        CompCluster.body_style == listing.body_style,
        CompCluster.transmission == listing.transmission,
        CompCluster.currency == listing.currency,
    )
    if listing.generation:
        stmt = stmt.where(
            CompCluster.generation == listing.generation,
            CompCluster.year_bucket.is_(None),
        )
    else:
        stmt = stmt.where(
            CompCluster.generation.is_(None),
            CompCluster.year_bucket == listing.year,
        )

    return await session.scalar(stmt)


async def _clusters_for(
    session,
    listings: list[Listing],
) -> dict[tuple[str, str, str | None, int | None, str, str, str], CompCluster]:
    """Fetch matching comp clusters for a page of listings in one query."""
    generation_keys: set[tuple[str, str, str, str, str, str]] = set()
    year_bucket_keys: set[tuple[str, str, int, str, str, str]] = set()

    for listing in listings:
        key = _listing_cluster_key(listing)
        if key is None:
            continue
        make, model, generation, year_bucket, body_style, transmission, currency = key
        if generation is not None:
            generation_keys.add((make, model, generation, body_style, transmission, currency))
        elif year_bucket is not None:
            year_bucket_keys.add((make, model, year_bucket, body_style, transmission, currency))

    if not generation_keys and not year_bucket_keys:
        return {}

    clauses = []
    if generation_keys:
        clauses.append(
            and_(
                tuple_(
                    func.lower(CompCluster.make),
                    func.lower(CompCluster.model),
                    CompCluster.generation,
                    CompCluster.body_style,
                    CompCluster.transmission,
                    CompCluster.currency,
                ).in_(list(generation_keys)),
                CompCluster.year_bucket.is_(None),
            )
        )
    if year_bucket_keys:
        clauses.append(
            and_(
                tuple_(
                    func.lower(CompCluster.make),
                    func.lower(CompCluster.model),
                    CompCluster.year_bucket,
                    CompCluster.body_style,
                    CompCluster.transmission,
                    CompCluster.currency,
                ).in_(list(year_bucket_keys)),
                CompCluster.generation.is_(None),
            )
        )

    result = await session.execute(select(CompCluster).where(or_(*clauses)))
    clusters = result.scalars().all()
    return {
        key: cluster
        for cluster in clusters
        if (key := _cluster_lookup_key(cluster)) is not None
    }


def _listing_cluster_key(
    listing: Listing,
) -> tuple[str, str, str | None, int | None, str, str, str] | None:
    if not (listing.make and listing.model and listing.body_style and listing.transmission):
        return None

    make = listing.make.strip().lower()
    model = listing.model.strip().lower()
    body_style = listing.body_style.value if hasattr(listing.body_style, "value") else str(listing.body_style)
    transmission = (
        listing.transmission.value
        if hasattr(listing.transmission, "value")
        else str(listing.transmission)
    )
    currency = listing.currency.value if hasattr(listing.currency, "value") else str(listing.currency)
    generation = (
        listing.generation.value if hasattr(listing.generation, "value") else listing.generation
    )
    year_bucket = None if generation else listing.year
    return make, model, generation, year_bucket, body_style, transmission, currency


def _cluster_lookup_key(
    cluster: CompCluster,
) -> tuple[str, str, str | None, int | None, str, str, str] | None:
    if not (cluster.make and cluster.model and cluster.body_style and cluster.transmission):
        return None

    make = cluster.make.strip().lower()
    model = cluster.model.strip().lower()
    body_style = (
        cluster.body_style.value if hasattr(cluster.body_style, "value") else str(cluster.body_style)
    )
    transmission = (
        cluster.transmission.value
        if hasattr(cluster.transmission, "value")
        else str(cluster.transmission)
    )
    currency = cluster.currency.value if hasattr(cluster.currency, "value") else str(cluster.currency)
    generation = (
        cluster.generation.value if hasattr(cluster.generation, "value") else cluster.generation
    )
    return make, model, generation, cluster.year_bucket, body_style, transmission, currency


def _enrich(listing: Listing, cluster: CompCluster | None) -> ListingOut:
    """Build a ListingOut, injecting cluster_median and delta_pct."""
    data = {column.key: getattr(listing, column.key) for column in listing.__table__.columns}

    cluster_median: float | None = None
    delta_pct: float | None = None

    if cluster and cluster.median_price and not cluster.insufficient_data:
        cluster_median = float(cluster.median_price)
        reference_price = listing.current_bid if listing.current_bid is not None else listing.asking_price
        if reference_price is not None:
            delta_pct = round(
                (float(reference_price) - cluster_median) / cluster_median * 100,
                1,
            )

    data["cluster_median"] = cluster_median
    data["cluster_comp_count"] = int(cluster.comp_count) if cluster else None
    data["cluster_p25"] = float(cluster.p25_price) if cluster and cluster.p25_price is not None else None
    data["cluster_p75"] = float(cluster.p75_price) if cluster and cluster.p75_price is not None else None
    data["cluster_min"] = float(cluster.min_price) if cluster and cluster.min_price is not None else None
    data["cluster_max"] = float(cluster.max_price) if cluster and cluster.max_price is not None else None
    data["cluster_window_days"] = int(cluster.window_days) if cluster else None
    data["delta_pct"] = delta_pct
    return ListingOut.model_validate(data)
