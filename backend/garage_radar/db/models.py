"""
Garage Radar — SQLAlchemy 2.0 ORM models.
These are the authoritative schema definition; Alembic migrations are generated from them.

General-purpose vintage car market intelligence platform.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Enums ────────────────────────────────────────────────────────────────────

class SourceEnum(str, enum.Enum):
    bat = "bat"
    carsandbids = "carsandbids"
    pcarmarket = "pcarmarket"
    ebay = "ebay"
    dealer_manual = "dealer_manual"
    manual = "manual"


class ListingStatusEnum(str, enum.Enum):
    active = "active"
    ended = "ended"
    sold = "sold"
    removed = "removed"
    relist = "relist"


class BodyStyleEnum(str, enum.Enum):
    coupe = "coupe"
    targa = "targa"
    cabriolet = "cabriolet"
    speedster = "speedster"
    convertible = "convertible"
    roadster = "roadster"
    fastback = "fastback"
    hardtop = "hardtop"
    sedan = "sedan"
    wagon = "wagon"
    pickup = "pickup"


class TransmissionEnum(str, enum.Enum):
    manual = "manual"
    manual_6sp = "manual-6sp"
    auto = "auto"


class DrivetrainEnum(str, enum.Enum):
    rwd = "rwd"
    awd = "awd"
    fwd = "fwd"


class TitleStatusEnum(str, enum.Enum):
    clean = "clean"
    salvage = "salvage"
    unknown = "unknown"


class CurrencyEnum(str, enum.Enum):
    USD = "USD"
    GBP = "GBP"
    EUR = "EUR"


class PriceTypeEnum(str, enum.Enum):
    auction_final = "auction_final"
    dealer_ask = "dealer_ask"
    private_ask = "private_ask"
    estimate = "estimate"


class AlertTypeEnum(str, enum.Enum):
    underpriced = "underpriced"
    price_drop = "price_drop"
    new_listing = "new_listing"
    relist = "relist"
    insufficient_data_warning = "insufficient_data_warning"


class AlertSeverityEnum(str, enum.Enum):
    info = "info"
    watch = "watch"
    act = "act"


class AlertStatusEnum(str, enum.Enum):
    open = "open"
    read = "read"
    dismissed = "dismissed"


class SellerTypeEnum(str, enum.Enum):
    dealer = "dealer"
    private = "private"
    auction_house = "auction_house"


class ColorCanonicalEnum(str, enum.Enum):
    white = "white"
    silver = "silver"
    grey = "grey"
    grey_metallic = "grey-metallic"
    black = "black"
    red = "red"
    blue = "blue"
    blue_metallic = "blue-metallic"
    green = "green"
    green_metallic = "green-metallic"
    yellow = "yellow"
    orange = "orange"
    brown = "brown"
    beige = "beige"
    gold_metallic = "gold-metallic"
    purple = "purple"
    turquoise = "turquoise"
    burgundy = "burgundy"
    bronze_metallic = "bronze-metallic"
    other = "other"


# ── Base ─────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Models ───────────────────────────────────────────────────────────────────

class Listing(Base):
    """
    Active and historical asks / listings.
    Natural key: (source, source_url).
    """
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source", "source_url", name="uq_listings_source_url"),
        CheckConstraint("mileage >= 0", name="ck_listings_mileage_positive"),
        CheckConstraint(
            "normalization_confidence BETWEEN 0 AND 1",
            name="ck_listings_confidence_range",
        ),
        Index("idx_listings_make_model", "make", "model"),
        Index("idx_listings_year", "year"),
        Index("idx_listings_status", "listing_status"),
        Index("idx_listings_source", "source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[SourceEnum] = mapped_column(
        Enum(SourceEnum, name="source_enum"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    scrape_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    listing_status: Mapped[ListingStatusEnum] = mapped_column(
        Enum(ListingStatusEnum, name="listing_status_enum"),
        nullable=False,
        default=ListingStatusEnum.active,
    )

    # Vehicle identity
    make: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    generation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_style: Mapped[Optional[BodyStyleEnum]] = mapped_column(
        Enum(BodyStyleEnum, name="body_style_enum"), nullable=True
    )
    trim: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    drivetrain: Mapped[DrivetrainEnum] = mapped_column(
        Enum(DrivetrainEnum, name="drivetrain_enum"),
        nullable=False,
        default=DrivetrainEnum.rwd,
    )
    engine_variant: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transmission: Mapped[Optional[TransmissionEnum]] = mapped_column(
        Enum(TransmissionEnum, name="transmission_enum"), nullable=True
    )
    exterior_color_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exterior_color_canonical: Mapped[Optional[ColorCanonicalEnum]] = mapped_column(
        Enum(ColorCanonicalEnum, name="color_canonical_enum"), nullable=True
    )
    interior_color_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mileage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vin: Mapped[Optional[str]] = mapped_column(String(17), nullable=True)
    title_status: Mapped[TitleStatusEnum] = mapped_column(
        Enum(TitleStatusEnum, name="title_status_enum"),
        nullable=False,
        default=TitleStatusEnum.unknown,
    )

    # Price
    asking_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[CurrencyEnum] = mapped_column(
        Enum(CurrencyEnum, name="currency_enum"),
        nullable=False,
        default=CurrencyEnum.USD,
    )
    price_history: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True, default=list
    )
    final_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # NLP signals
    matching_numbers: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    original_paint: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    service_history: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    modification_flags: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    normalization_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Raw / meta
    description_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    listing_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    seller_type: Mapped[Optional[SellerTypeEnum]] = mapped_column(
        Enum(SellerTypeEnum, name="seller_type_enum"), nullable=True
    )
    seller_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bidder_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    snapshot_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    possible_duplicate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id"), nullable=True
    )
    title_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    alerts: Mapped[list["Alert"]] = relationship("Alert", back_populates="listing")


class Comp(Base):
    """
    Completed sales — the comp database.
    Natural key: (source, source_url).
    """
    __tablename__ = "comps"
    __table_args__ = (
        UniqueConstraint("source", "source_url", name="uq_comps_source_url"),
        Index("idx_comps_sale_date", "sale_date"),
        Index("idx_comps_make_model_body_trans", "make", "model", "body_style", "transmission"),
        Index("idx_comps_price_type", "price_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[SourceEnum] = mapped_column(
        Enum(SourceEnum, name="source_enum"), nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    make: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    generation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_style: Mapped[Optional[BodyStyleEnum]] = mapped_column(
        Enum(BodyStyleEnum, name="body_style_enum"), nullable=True
    )
    trim: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transmission: Mapped[Optional[TransmissionEnum]] = mapped_column(
        Enum(TransmissionEnum, name="transmission_enum"), nullable=True
    )
    engine_variant: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exterior_color_canonical: Mapped[Optional[ColorCanonicalEnum]] = mapped_column(
        Enum(ColorCanonicalEnum, name="color_canonical_enum"), nullable=True
    )
    exterior_color_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mileage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    sale_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    sale_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    price_type: Mapped[PriceTypeEnum] = mapped_column(
        Enum(PriceTypeEnum, name="price_type_enum"),
        nullable=False,
        default=PriceTypeEnum.auction_final,
    )
    currency: Mapped[CurrencyEnum] = mapped_column(
        Enum(CurrencyEnum, name="currency_enum"),
        nullable=False,
        default=CurrencyEnum.USD,
    )
    bidder_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    matching_numbers: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    original_paint: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    service_history: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    modification_flags: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CompCluster(Base):
    """Pre-computed price bands per spec cluster. Rebuilt nightly."""
    __tablename__ = "comp_clusters"
    __table_args__ = (
        UniqueConstraint("cluster_key", name="uq_comp_clusters_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_key: Mapped[str] = mapped_column(Text, nullable=False)  # 'Porsche:911:coupe:manual'
    make: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    body_style: Mapped[BodyStyleEnum] = mapped_column(
        Enum(BodyStyleEnum, name="body_style_enum"), nullable=False
    )
    transmission: Mapped[TransmissionEnum] = mapped_column(
        Enum(TransmissionEnum, name="transmission_enum"), nullable=False
    )
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    comp_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    median_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    p25_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    p75_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    min_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    max_price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    avg_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    insufficient_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Alert(Base):
    """Signals worth surfacing to the user."""
    __tablename__ = "alerts"
    __table_args__ = (
        Index("idx_alerts_status", "status"),
        Index("idx_alerts_triggered_at", "triggered_at"),
        Index("idx_alerts_listing_id", "listing_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    alert_type: Mapped[AlertTypeEnum] = mapped_column(
        Enum(AlertTypeEnum, name="alert_type_enum"), nullable=False
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    listing_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    delta_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    severity: Mapped[AlertSeverityEnum] = mapped_column(
        Enum(AlertSeverityEnum, name="alert_severity_enum"),
        nullable=False,
        default=AlertSeverityEnum.info,
    )
    status: Mapped[AlertStatusEnum] = mapped_column(
        Enum(AlertStatusEnum, name="alert_status_enum"),
        nullable=False,
        default=AlertStatusEnum.open,
    )
    notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    listing: Mapped[Optional["Listing"]] = relationship("Listing", back_populates="alerts")


class CanonicalModel(Base):
    """Reference table: known make/model spec configurations. Pre-seeded; rarely changes."""
    __tablename__ = "canonical_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    make: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    generation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    years_start: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    years_end: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    common_name: Mapped[str] = mapped_column(Text, nullable=False)
    known_trims: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text), nullable=True)
    known_engine_variants: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(Text), nullable=True
    )
    comp_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PipelineLog(Base):
    """Crawl run health tracking."""
    __tablename__ = "pipeline_log"
    __table_args__ = (
        Index("idx_pipeline_log_source", "source", "run_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[SourceEnum] = mapped_column(
        Enum(SourceEnum, name="source_enum"), nullable=False
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    pages_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_extracted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extraction_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalization_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_s: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
