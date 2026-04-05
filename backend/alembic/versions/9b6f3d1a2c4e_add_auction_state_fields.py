"""add auction state fields

Revision ID: 9b6f3d1a2c4e
Revises: c4e2f8b91a6d
Create Date: 2026-03-29 21:15:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9b6f3d1a2c4e"
down_revision = "c4e2f8b91a6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("current_bid", sa.Numeric(10, 2), nullable=True))
    op.add_column("listings", sa.Column("auction_end_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("listings", sa.Column("time_remaining_text", sa.Text(), nullable=True))

    op.execute("DROP VIEW IF EXISTS active_listings_with_delta")
    op.execute(
        """
        CREATE VIEW active_listings_with_delta AS
        SELECT
            l.id,
            l.source,
            l.source_url,
            l.year,
            l.make,
            l.model,
            l.generation,
            l.body_style,
            l.transmission,
            l.current_bid,
            l.asking_price,
            l.auction_end_at,
            l.time_remaining_text,
            l.listing_status,
            l.location,
            l.mileage,
            l.exterior_color_canonical,
            l.normalization_confidence,
            l.price_history,
            l.created_at,
            cc.median_price      AS cluster_median,
            cc.p25_price         AS cluster_p25,
            cc.p75_price         AS cluster_p75,
            cc.insufficient_data AS cluster_insufficient_data,
            CASE
                WHEN cc.median_price IS NOT NULL
                    AND COALESCE(l.current_bid, l.asking_price) IS NOT NULL
                THEN ROUND(
                    ((COALESCE(l.current_bid, l.asking_price) - cc.median_price) / cc.median_price * 100)::numeric,
                    1
                )
                ELSE NULL
            END AS delta_pct
        FROM listings l
        LEFT JOIN comp_clusters cc
            ON lower(cc.make) = lower(l.make)
            AND lower(cc.model) = lower(l.model)
            AND cc.body_style = l.body_style
            AND cc.transmission = l.transmission
            AND (
                (
                    l.generation IS NOT NULL
                    AND cc.generation = l.generation
                    AND cc.year_bucket IS NULL
                )
                OR (
                    l.generation IS NULL
                    AND cc.generation IS NULL
                    AND cc.year_bucket = l.year
                )
            )
        WHERE l.listing_status IN ('active', 'relist')
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS active_listings_with_delta")
    op.execute(
        """
        CREATE VIEW active_listings_with_delta AS
        SELECT
            l.id,
            l.source,
            l.source_url,
            l.year,
            l.make,
            l.model,
            l.generation,
            l.body_style,
            l.transmission,
            l.asking_price,
            l.listing_status,
            l.location,
            l.mileage,
            l.exterior_color_canonical,
            l.normalization_confidence,
            l.price_history,
            l.created_at,
            cc.median_price      AS cluster_median,
            cc.p25_price         AS cluster_p25,
            cc.p75_price         AS cluster_p75,
            cc.insufficient_data AS cluster_insufficient_data,
            CASE
                WHEN cc.median_price IS NOT NULL AND l.asking_price IS NOT NULL
                THEN ROUND(
                    ((l.asking_price - cc.median_price) / cc.median_price * 100)::numeric,
                    1
                )
                ELSE NULL
            END AS delta_pct
        FROM listings l
        LEFT JOIN comp_clusters cc
            ON lower(cc.make) = lower(l.make)
            AND lower(cc.model) = lower(l.model)
            AND cc.body_style = l.body_style
            AND cc.transmission = l.transmission
            AND (
                (
                    l.generation IS NOT NULL
                    AND cc.generation = l.generation
                    AND cc.year_bucket IS NULL
                )
                OR (
                    l.generation IS NULL
                    AND cc.generation IS NULL
                    AND cc.year_bucket = l.year
                )
            )
        WHERE l.listing_status IN ('active', 'relist')
        """
    )

    op.drop_column("listings", "time_remaining_text")
    op.drop_column("listings", "auction_end_at")
    op.drop_column("listings", "current_bid")
