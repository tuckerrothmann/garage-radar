"""initial_schema

Revision ID: e09629634686
Revises:
Create Date: 2026-03-22 22:52:54.324319

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e09629634686'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# All 14 ENUM types: name → values (matches garage_radar/db/models.py exactly)
_ENUMS = {
    "source_enum": ("bat", "carsandbids", "pcarmarket", "ebay", "dealer_manual", "manual"),
    "listing_status_enum": ("active", "ended", "sold", "removed", "relist"),
    "generation_enum": ("G1", "G2", "G3", "G4", "G5", "G6"),
    "body_style_enum": ("coupe", "targa", "cabriolet", "speedster"),
    "transmission_enum": ("manual", "manual-6sp", "auto"),
    "drivetrain_enum": ("rwd", "awd"),
    "title_status_enum": ("clean", "salvage", "unknown"),
    "currency_enum": ("USD", "GBP", "EUR"),
    "price_type_enum": ("auction_final", "dealer_ask", "private_ask", "estimate"),
    "alert_type_enum": (
        "underpriced", "price_drop", "new_listing", "relist",
        "insufficient_data_warning",
    ),
    "alert_severity_enum": ("info", "watch", "act"),
    "alert_status_enum": ("open", "read", "dismissed"),
    "seller_type_enum": ("dealer", "private", "auction_house"),
    "color_canonical_enum": (
        "white", "silver", "grey", "grey-metallic", "black", "red",
        "blue", "blue-metallic", "green", "green-metallic", "yellow",
        "orange", "brown", "beige", "gold-metallic", "purple",
        "turquoise", "burgundy", "bronze-metallic", "other",
    ),
}


def _enum_type(name: str, *, create_type: bool = False) -> ENUM:
    return ENUM(*_ENUMS[name], name=name, create_type=create_type)


def upgrade() -> None:
    conn = op.get_bind()

    # pgcrypto supplies gen_random_uuid() as a belt-and-suspenders fallback
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── ENUM types ──────────────────────────────────────────────────────────
    for name, _values in _ENUMS.items():
        _enum_type(name, create_type=True).create(conn, checkfirst=True)

    # ── listings ────────────────────────────────────────────────────────────
    # Self-referential FK (possible_duplicate_id) is fine inside create_table;
    # Postgres accepts forward refs to the same table being created.
    op.create_table(
        "listings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source", _enum_type("source_enum"), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column(
            "scrape_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "listing_status",
            _enum_type("listing_status_enum"),
            nullable=False,
            server_default="active",
        ),
        # Vehicle
        sa.Column("year", sa.SmallInteger, nullable=False),
        sa.Column("generation", _enum_type("generation_enum"), nullable=True),
        sa.Column("body_style", _enum_type("body_style_enum"), nullable=True),
        sa.Column("trim", sa.Text, nullable=True),
        sa.Column(
            "drivetrain",
            _enum_type("drivetrain_enum"),
            nullable=False,
            server_default="rwd",
        ),
        sa.Column("engine_variant", sa.Text, nullable=True),
        sa.Column("transmission", _enum_type("transmission_enum"), nullable=True),
        sa.Column("exterior_color_raw", sa.Text, nullable=True),
        sa.Column(
            "exterior_color_canonical",
            _enum_type("color_canonical_enum"),
            nullable=True,
        ),
        sa.Column("interior_color_raw", sa.Text, nullable=True),
        sa.Column("mileage", sa.Integer, nullable=True),
        sa.Column("vin", sa.String(17), nullable=True),
        sa.Column(
            "title_status",
            _enum_type("title_status_enum"),
            nullable=False,
            server_default="unknown",
        ),
        # Price
        sa.Column("asking_price", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "currency",
            _enum_type("currency_enum"),
            nullable=False,
            server_default="USD",
        ),
        sa.Column("price_history", JSONB, nullable=True),
        sa.Column("final_price", sa.Numeric(10, 2), nullable=True),
        # NLP signals
        sa.Column("matching_numbers", sa.Boolean, nullable=True),
        sa.Column("original_paint", sa.Boolean, nullable=True),
        sa.Column("service_history", sa.Boolean, nullable=True),
        sa.Column("modification_flags", ARRAY(sa.Text), nullable=True),
        sa.Column("normalization_confidence", sa.Float, nullable=True),
        # Raw / meta
        sa.Column("description_raw", sa.Text, nullable=True),
        sa.Column("listing_date", sa.Date, nullable=True),
        sa.Column("seller_type", _enum_type("seller_type_enum"), nullable=True),
        sa.Column("seller_name", sa.Text, nullable=True),
        sa.Column("location", sa.Text, nullable=True),
        sa.Column("bidder_count", sa.Integer, nullable=True),
        sa.Column("snapshot_path", sa.Text, nullable=True),
        sa.Column(
            "possible_duplicate_id",
            UUID(as_uuid=True),
            sa.ForeignKey("listings.id"),
            nullable=True,
        ),
        sa.Column("title_raw", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Constraints
        sa.UniqueConstraint("source", "source_url", name="uq_listings_source_url"),
        sa.CheckConstraint("year BETWEEN 1965 AND 1998", name="ck_listings_year_range"),
        sa.CheckConstraint("mileage >= 0", name="ck_listings_mileage_positive"),
        sa.CheckConstraint(
            "normalization_confidence BETWEEN 0 AND 1",
            name="ck_listings_confidence_range",
        ),
    )
    op.create_index("idx_listings_generation", "listings", ["generation"])
    op.create_index("idx_listings_year", "listings", ["year"])
    op.create_index("idx_listings_status", "listings", ["listing_status"])
    op.create_index("idx_listings_source", "listings", ["source"])

    # ── comps ────────────────────────────────────────────────────────────────
    op.create_table(
        "comps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source", _enum_type("source_enum"), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("year", sa.SmallInteger, nullable=False),
        sa.Column("generation", _enum_type("generation_enum"), nullable=True),
        sa.Column("body_style", _enum_type("body_style_enum"), nullable=True),
        sa.Column("trim", sa.Text, nullable=True),
        sa.Column("transmission", _enum_type("transmission_enum"), nullable=True),
        sa.Column("engine_variant", sa.Text, nullable=True),
        sa.Column(
            "exterior_color_canonical",
            _enum_type("color_canonical_enum"),
            nullable=True,
        ),
        sa.Column("exterior_color_raw", sa.Text, nullable=True),
        sa.Column("mileage", sa.Integer, nullable=True),
        sa.Column("sale_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("sale_date", sa.Date, nullable=True),
        sa.Column(
            "price_type",
            _enum_type("price_type_enum"),
            nullable=False,
            server_default="auction_final",
        ),
        sa.Column(
            "currency",
            _enum_type("currency_enum"),
            nullable=False,
            server_default="USD",
        ),
        sa.Column("bidder_count", sa.Integer, nullable=True),
        sa.Column("matching_numbers", sa.Boolean, nullable=True),
        sa.Column("original_paint", sa.Boolean, nullable=True),
        sa.Column("service_history", sa.Boolean, nullable=True),
        sa.Column("modification_flags", ARRAY(sa.Text), nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("source", "source_url", name="uq_comps_source_url"),
    )
    op.create_index("idx_comps_sale_date", "comps", ["sale_date"])
    op.create_index(
        "idx_comps_generation_body_trans",
        "comps",
        ["generation", "body_style", "transmission"],
    )
    op.create_index("idx_comps_price_type", "comps", ["price_type"])

    # ── comp_clusters ────────────────────────────────────────────────────────
    op.create_table(
        "comp_clusters",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("cluster_key", sa.Text, nullable=False),
        sa.Column("generation", _enum_type("generation_enum"), nullable=False),
        sa.Column("body_style", _enum_type("body_style_enum"), nullable=False),
        sa.Column("transmission", _enum_type("transmission_enum"), nullable=False),
        sa.Column("window_days", sa.Integer, nullable=False, server_default="90"),
        sa.Column("comp_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("median_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("p25_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("p75_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("min_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("max_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("avg_confidence", sa.Float, nullable=True),
        sa.Column("insufficient_data", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "last_computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("cluster_key", name="uq_comp_clusters_key"),
    )

    # ── alerts ───────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("alert_type", _enum_type("alert_type_enum"), nullable=False),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("listings.id"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("delta_pct", sa.Float, nullable=True),
        sa.Column(
            "severity",
            _enum_type("alert_severity_enum"),
            nullable=False,
            server_default="info",
        ),
        sa.Column(
            "status",
            _enum_type("alert_status_enum"),
            nullable=False,
            server_default="open",
        ),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_alerts_status", "alerts", ["status"])
    op.create_index("idx_alerts_triggered_at", "alerts", ["triggered_at"])
    op.create_index("idx_alerts_listing_id", "alerts", ["listing_id"])

    # ── canonical_models ─────────────────────────────────────────────────────
    op.create_table(
        "canonical_models",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("generation", _enum_type("generation_enum"), nullable=False),
        sa.Column("years_start", sa.SmallInteger, nullable=False),
        sa.Column("years_end", sa.SmallInteger, nullable=False),
        sa.Column("common_name", sa.Text, nullable=False),
        sa.Column("known_trims", ARRAY(sa.Text), nullable=True),
        sa.Column("known_engine_variants", ARRAY(sa.Text), nullable=True),
        sa.Column("comp_weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # ── pipeline_log ─────────────────────────────────────────────────────────
    op.create_table(
        "pipeline_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source", _enum_type("source_enum"), nullable=False),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("pages_fetched", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_extracted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("extraction_errors", sa.Integer, nullable=False, server_default="0"),
        sa.Column("normalization_errors", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duration_s", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )
    op.create_index("idx_pipeline_log_source", "pipeline_log", ["source", "run_at"])

    # ── active_listings_with_delta view ─────────────────────────────────────
    # Shows active listings annotated with their comp cluster's price band and
    # the % delta between asking_price and cluster median.
    op.execute("""
        CREATE OR REPLACE VIEW active_listings_with_delta AS
        SELECT
            l.id,
            l.source,
            l.source_url,
            l.year,
            l.generation,
            l.body_style,
            l.transmission,
            l.asking_price,
            l.listing_status,
            l.location,
            l.mileage,
            l.exterior_color_canonical,
            l.normalization_confidence,
            cc.median_price         AS cluster_median,
            cc.p25_price            AS cluster_p25,
            cc.p75_price            AS cluster_p75,
            cc.insufficient_data    AS cluster_insufficient_data,
            CASE
                WHEN cc.median_price IS NOT NULL AND l.asking_price IS NOT NULL
                THEN ROUND(
                    ((l.asking_price - cc.median_price) / cc.median_price * 100)::numeric,
                    1
                )
                ELSE NULL
            END                     AS delta_pct
        FROM listings l
        LEFT JOIN comp_clusters cc
            ON  cc.generation  = l.generation
            AND cc.body_style   = l.body_style
            AND cc.transmission = l.transmission
        WHERE l.listing_status = 'active'
    """)


def downgrade() -> None:
    conn = op.get_bind()

    op.execute("DROP VIEW IF EXISTS active_listings_with_delta")

    # Tables in reverse dependency order (alerts → listings last)
    op.drop_table("pipeline_log")
    op.drop_table("canonical_models")
    op.drop_table("alerts")
    op.drop_table("comp_clusters")
    op.drop_table("comps")
    op.drop_table("listings")

    # ENUM types — drop in reverse creation order
    for name in reversed(list(_ENUMS.keys())):
        _enum_type(name, create_type=False).drop(conn, checkfirst=True)
