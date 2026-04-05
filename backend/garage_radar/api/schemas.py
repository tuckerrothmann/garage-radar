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
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Listings ──────────────────────────────────────────────────────────────────

class ListingOut(_Base):
    id: uuid.UUID
    source: str
    source_url: str
    listing_status: str
    year: int
    make: str | None = None
    model: str | None = None
    generation: str | None = None
    body_style: str | None = None
    trim: str | None = None
    drivetrain: str
    transmission: str | None = None
    engine_variant: str | None = None
    exterior_color_canonical: str | None = None
    exterior_color_raw: str | None = None
    interior_color_raw: str | None = None
    mileage: int | None = None
    vin: str | None = None
    title_status: str
    current_bid: float | None = None
    asking_price: float | None = None
    currency: str
    final_price: float | None = None
    matching_numbers: bool | None = None
    original_paint: bool | None = None
    service_history: bool | None = None
    modification_flags: list[str] | None = None
    normalization_confidence: float | None = None
    listing_date: date | None = None
    auction_end_at: datetime | None = None
    time_remaining_text: str | None = None
    seller_type: str | None = None
    seller_name: str | None = None
    location: str | None = None
    bidder_count: int | None = None
    title_raw: str | None = None
    created_at: datetime
    updated_at: datetime
    # Enriched: injected by the listings router via cluster join
    cluster_median: float | None = None
    cluster_comp_count: int | None = None
    cluster_p25: float | None = None
    cluster_p75: float | None = None
    cluster_min: float | None = None
    cluster_max: float | None = None
    cluster_window_days: int | None = None
    delta_pct: float | None = None


class ListingDetailOut(ListingOut):
    """Single-listing response: includes price history and open alerts."""
    price_history: list[dict[str, Any]] | None = None
    alerts: list[AlertOut] = Field(default_factory=list)


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
    make: str | None = None
    model: str | None = None
    generation: str | None = None
    body_style: str | None = None
    trim: str | None = None
    transmission: str | None = None
    engine_variant: str | None = None
    exterior_color_canonical: str | None = None
    exterior_color_raw: str | None = None
    mileage: int | None = None
    sale_price: float | None = None
    sale_date: date | None = None
    price_type: str
    currency: str
    bidder_count: int | None = None
    matching_numbers: bool | None = None
    original_paint: bool | None = None
    service_history: bool | None = None
    modification_flags: list[str] | None = None
    confidence_score: float | None = None
    notes: str | None = None
    created_at: datetime


class CompPage(_Base):
    total: int
    limit: int
    offset: int
    items: list[CompOut]


class CompClusterOut(_Base):
    id: int
    cluster_key: str
    make: str | None = None
    model: str | None = None
    generation: str | None = None
    year_bucket: int | None = None
    body_style: str
    transmission: str
    currency: str
    window_days: int
    comp_count: int
    median_price: float | None = None
    p25_price: float | None = None
    p75_price: float | None = None
    min_price: float | None = None
    max_price: float | None = None
    avg_confidence: float | None = None
    insufficient_data: bool
    last_computed_at: datetime


class VehicleProfileStatsOut(_Base):
    listing_count: int
    comp_count: int
    primary_currency: str | None = None
    currencies: list[str] = Field(default_factory=list)
    year_min: int | None = None
    year_max: int | None = None
    avg_asking_price: float | None = None
    min_asking_price: float | None = None
    max_asking_price: float | None = None
    avg_sale_price: float | None = None
    min_sale_price: float | None = None
    max_sale_price: float | None = None
    latest_listing_at: datetime | None = None
    latest_sale_date: date | None = None
    sources: list[str] = Field(default_factory=list)


class VehicleProfileReferenceOut(_Base):
    name: str
    url: str
    license: str | None = None


class VehicleProfileSectionOut(_Base):
    title: str
    summary: str
    source_name: str
    source_url: str | None = None


class VehicleProfileCountOut(_Base):
    label: str
    count: int


class VehicleProfileRecentListingOut(_Base):
    id: uuid.UUID
    title: str
    source: str
    source_url: str
    year: int
    price: float | None = None
    currency: str | None = None
    listing_status: str
    location: str | None = None


class VehicleProfileRecentSaleOut(_Base):
    id: uuid.UUID
    title: str
    source: str
    source_url: str
    year: int
    sale_price: float | None = None
    currency: str | None = None
    sale_date: date | None = None


class VehicleProfileOut(_Base):
    make: str
    model: str
    year: int | None = None
    slug: str
    display_name: str
    profile_source: str
    overview: str
    canonical_url: str | None = None
    hero_image_url: str | None = None
    production_years: str | None = None
    body_styles: list[str] = Field(default_factory=list)
    transmissions: list[str] = Field(default_factory=list)
    notable_trims: list[str] = Field(default_factory=list)
    encyclopedia_facts: dict[str, str] = Field(default_factory=dict)
    market_facts: dict[str, str] = Field(default_factory=dict)
    quick_facts: dict[str, str] = Field(default_factory=dict)
    highlights: list[str] = Field(default_factory=list)
    common_questions: list[str] = Field(default_factory=list)
    buying_tips: list[str] = Field(default_factory=list)
    market_summary: str
    market_signals: list[str] = Field(default_factory=list)
    recent_sales_scope: str | None = None
    reference_links: list[VehicleProfileReferenceOut] = Field(default_factory=list)
    external_sections: list[VehicleProfileSectionOut] = Field(default_factory=list)
    local_observations: list[str] = Field(default_factory=list)
    source_breakdown: list[VehicleProfileCountOut] = Field(default_factory=list)
    related_model_breakdown: list[VehicleProfileCountOut] = Field(default_factory=list)
    year_breakdown: list[VehicleProfileCountOut] = Field(default_factory=list)
    body_style_breakdown: list[VehicleProfileCountOut] = Field(default_factory=list)
    transmission_breakdown: list[VehicleProfileCountOut] = Field(default_factory=list)
    trim_breakdown: list[VehicleProfileCountOut] = Field(default_factory=list)
    recent_listings: list[VehicleProfileRecentListingOut] = Field(default_factory=list)
    recent_sales: list[VehicleProfileRecentSaleOut] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    stats: VehicleProfileStatsOut


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertOut(_Base):
    id: uuid.UUID
    alert_type: str
    triggered_at: datetime
    listing_id: uuid.UUID | None = None
    reason: str
    delta_pct: float | None = None
    severity: str
    status: str
    notified_at: datetime | None = None


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
