"""
Listings router — GET /listings, GET /listings/{id}

Filter params: make, model, generation, body_style, transmission, status, source,
               year_min, year_max, price_min, price_max,
               confidence_min (0.0–1.0)
Pagination:    limit (max 200, default 50), offset (default 0)

Each listing response includes cluster_median and delta_pct from the
comp_clusters table so callers can render a price-vs-market indicator
without a second round-trip.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from garage_radar.api.deps import DBSession
from garage_radar.api.schemas import ListingDetailOut, ListingOut, ListingPage
from garage_radar.db.models import (
    Alert,
    AlertStatusEnum,
    BodyStyleEnum,
    CompCluster,
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
    make: Optional[str] = Query(None, description="e.g. Porsche"),
    model: Optional[str] = Query(None, description="e.g. 911"),
    generation: Optional[str] = Query(None, description="e.g. G6, C3 — free text"),
    body_style: Optional[str] = Query(None),
    transmission: Optional[str] = Query(None),
    status: Optional[str] = Query("active"),
    source: Optional[str] = Query(None),
    year_min: Optional[int] = Query(None, ge=1900, le=2030),
    year_max: Optional[int] = Query(None, ge=1900, le=2030),
    price_min: Optional[float] = Query(None, ge=0),
    price_max: Optional[float] = Query(None, ge=0),
    confidence_min: Optional[float] = Query(None, ge=0.0, le=1.0,
                                             description="Minimum normalization confidence (0–1)"),
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> ListingPage:
    """Return a paginated, filtered listing of vintage vehicles."""

    stmt = select(Listing)

    if make:
        stmt = stmt.where(Listing.make.ilike(f"%{make}%"))
    if model:
        stmt = stmt.where(Listing.model.ilike(f"%{model}%"))
    if generation:
        stmt = stmt.where(Listing.generation.ilike(f"%{generation}%"))
    if status:
        try:
            stmt = stmt.where(Listing.listing_status == ListingStatusEnum(status))
        except ValueError:
            raise HTTPException(400, f"Invalid status '{status}'")
    if body_style:
        try:
            stmt = stmt.where(Listing.body_style == BodyStyleEnum(body_style))
        except ValueError:
            raise HTTPException(400, f"Invalid body_style '{body_style}'")
    if transmission:
        try:
            stmt = stmt.where(Listing.transmission == TransmissionEnum(transmission))
        except ValueError:
            raise HTTPException(400, f"Invalid transmission '{transmission}'")
    if source:
        try:
            stmt = stmt.where(Listing.source == SourceEnum(source))
        except ValueError:
            raise HTTPException(400, f"Invalid source '{source}'")
    if year_min is not None:
        stmt = stmt.where(Listing.year >= year_min)
    if year_max is not None:
        stmt = stmt.where(Listing.year <= year_max)
    if price_min is not None:
        stmt = stmt.where(Listing.asking_price >= price_min)
    if price_max is not None:
        stmt = stmt.where(Listing.asking_price <= price_max)
    if confidence_min is not None:
        stmt = stmt.where(Listing.normalization_confidence >= confidence_min)

    count_result = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    total = count_result or 0

    stmt = stmt.order_by(Listing.created_at.desc()).offset(offset).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()

    items = [_enrich(r, await _cluster_for(session, r)) for r in rows]

    return ListingPage(total=total, limit=limit, offset=offset, items=items)


@router.get("/{listing_id}", response_model=ListingDetailOut)
async def get_listing(
    listing_id: uuid.UUID,
    session: DBSession,
) -> ListingDetailOut:
    """Return a single listing with price history and open alerts."""
    row = await session.scalar(
        select(Listing)
        .where(Listing.id == listing_id)
        .options(selectinload(Listing.alerts))
    )
    if row is None:
        raise HTTPException(404, "Listing not found")

    cluster = await _cluster_for(session, row)
    base = _enrich(row, cluster)

    open_alerts = [a for a in row.alerts if a.status != AlertStatusEnum.dismissed]

    return ListingDetailOut(
        **base.model_dump(),
        price_history=row.price_history,
        alerts=open_alerts,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _cluster_for(session, listing: Listing) -> Optional[CompCluster]:
    """Fetch the matching comp cluster for a listing, if it exists."""
    if not (listing.make and listing.model and listing.body_style and listing.transmission):
        return None
    return await session.scalar(
        select(CompCluster).where(
            CompCluster.make == listing.make,
            CompCluster.model == listing.model,
            CompCluster.body_style == listing.body_style,
            CompCluster.transmission == listing.transmission,
        )
    )


def _enrich(listing: Listing, cluster: Optional[CompCluster]) -> ListingOut:
    """Build a ListingOut, injecting cluster_median and delta_pct."""
    data = {
        c.key: getattr(listing, c.key)
        for c in listing.__table__.columns
    }

    cluster_median: Optional[float] = None
    delta_pct: Optional[float] = None

    if cluster and cluster.median_price and not cluster.insufficient_data:
        cluster_median = float(cluster.median_price)
        if listing.asking_price:
            delta_pct = round(
                (float(listing.asking_price) - cluster_median) / cluster_median * 100,
                1,
            )

    data["cluster_median"] = cluster_median
    data["delta_pct"] = delta_pct
    return ListingOut.model_validate(data)
