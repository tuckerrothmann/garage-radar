"""
Pydantic v2 response schemas for the Garage Radar REST API.

These are intentionally decoupled from the SQLAlchemy ORM models so that
the API surface can evolve independently of the DB schema. All fields are
Optional[X] unless they are guaranteed non-null in the DB.

Naming convention: <Model>Out for response shapes, <Model>Patch for request bodies.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_serializer


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Listings ──────────────────────────────────────────────────────────────────

class ListingOut(_Base):
    id: uuid.UUID
    source: str
    source_url: str
    listing_status: str
    year: int
    generation: Optional[str] = None
    body_style: Optional[str] = None
    trim: Optional[str] = None
    drivetrain: str
    transmission: Optional[str] = None
    engine_variant: Optional[str] = None
    exterior_color_canonical: Optional[str] = None
    exterior_color_raw: Optional[str] = None
    interior_color_raw: Optional[str] = None
    mileage: Optional[int] = None
    vin: Optional[str] = None
    title_status: str
    asking_price: Optional[float] = None
    currency: str
    final_price: Optional[float] = None
    matching_numbers: Optional[bool] = None
    original_paint: Optional[bool] = None
    service_history: Optional[bool] = None
    modification_flags: Optional[list[str]] = None
    normalization_confidence: Optional[float] = None
    listing_date: Optional[date] = None
    seller_type: Optional[str] = None
    seller_name: Optional[str] = None
    location: Optional[str] = None
    bidder_count: Optional[int] = None
    title_raw: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Enriched: injected by the listings router via cluster join
    cluster_median: Optional[float] = None
    delta_pct: Optional[float] = None


class ListingDetailOut(ListingOut):
    """Single-listing response: includes price history and open alerts."""
    price_history: Optional[list[dict[str, Any]]] = None
    alerts: list["AlertOut"] = []


class ListingPage(_Base):
    """Paginated listing response."""
    total: int
    limit: int
    offset: int
    items: list[ListingOut]


# ── Comps ─────────────────────────────────────────────────────────────────────

class CompOut(_Base):
    id: uuid.UUID
    source: str
    source_url: str
    year: int
    generation: Optional[str] = None
    body_style: Optional[str] = None
    trim: Optional[str] = None
    transmission: Optional[str] = None
    engine_variant: Optional[str] = None
    exterior_color_canonical: Optional[str] = None
    exterior_color_raw: Optional[str] = None
    mileage: Optional[int] = None
    sale_price: Optional[float] = None
    sale_date: Optional[date] = None
    price_type: str
    currency: str
    bidder_count: Optional[int] = None
    matching_numbers: Optional[bool] = None
    original_paint: Optional[bool] = None
    service_history: Optional[bool] = None
    modification_flags: Optional[list[str]] = None
    confidence_score: Optional[float] = None
    notes: Optional[str] = None
    created_at: datetime


class CompPage(_Base):
    total: int
    limit: int
    offset: int
    items: list[CompOut]


class CompClusterOut(_Base):
    id: int
    cluster_key: str
    generation: str
    body_style: str
    transmission: str
    window_days: int
    comp_count: int
    median_price: Optional[float] = None
    p25_price: Optional[float] = None
    p75_price: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    avg_confidence: Optional[float] = None
    insufficient_data: bool
    last_computed_at: datetime


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertOut(_Base):
    id: uuid.UUID
    alert_type: str
    triggered_at: datetime
    listing_id: Optional[uuid.UUID] = None
    reason: str
    delta_pct: Optional[float] = None
    severity: str
    status: str
    notified_at: Optional[datetime] = None


class AlertPage(_Base):
    total: int
    limit: int
    offset: int
    items: list[AlertOut]


class AlertStatusPatch(BaseModel):
    """Request body for PATCH /alerts/{id}/status."""
    status: str  # "read" | "dismissed"


# Forward ref resolution for ListingDetailOut.alerts
ListingDetailOut.model_rebuild()
