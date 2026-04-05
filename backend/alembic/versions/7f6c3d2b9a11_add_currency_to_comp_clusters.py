"""add currency to comp clusters

Revision ID: 7f6c3d2b9a11
Revises: c4e2f8b91a6d
Create Date: 2026-04-02 19:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7f6c3d2b9a11"
down_revision = "c4e2f8b91a6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "comp_clusters",
        sa.Column(
            "currency",
            sa.Enum("USD", "GBP", "EUR", name="currency_enum", create_type=False),
            nullable=False,
            server_default=sa.text("'USD'"),
        ),
    )
    op.execute("UPDATE comp_clusters SET currency = 'USD' WHERE currency IS NULL")
    op.execute(
        """
        UPDATE comp_clusters
        SET cluster_key = cluster_key || ':' || lower(currency::text)
        WHERE cluster_key !~ ':(usd|gbp|eur)$'
        """
    )
    op.alter_column("comp_clusters", "currency", server_default=None)

    op.drop_index("idx_comp_clusters_lookup", table_name="comp_clusters")
    op.create_index(
        "idx_comp_clusters_lookup",
        "comp_clusters",
        ["make", "model", "generation", "year_bucket", "body_style", "transmission", "currency"],
        unique=False,
    )

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
            l.currency,
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
            AND cc.currency = l.currency
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

    op.drop_index("idx_comp_clusters_lookup", table_name="comp_clusters")
    op.create_index(
        "idx_comp_clusters_lookup",
        "comp_clusters",
        ["make", "model", "generation", "year_bucket", "body_style", "transmission"],
        unique=False,
    )

    op.execute(
        """
        UPDATE comp_clusters
        SET cluster_key = regexp_replace(cluster_key, ':(usd|gbp|eur)$', '')
        """
    )
    op.drop_column("comp_clusters", "currency")

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
