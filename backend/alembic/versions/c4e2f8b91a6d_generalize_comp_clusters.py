"""generalize comp clusters

Revision ID: c4e2f8b91a6d
Revises: 7d4a8c2b1f70
Create Date: 2026-03-25 23:45:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4e2f8b91a6d"
down_revision = "7d4a8c2b1f70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for value in ("sedan", "wagon", "hatchback", "suv", "truck", "van"):
        op.execute(f"ALTER TYPE body_style_enum ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("comp_clusters", sa.Column("make", sa.String(length=64), nullable=True))
    op.add_column("comp_clusters", sa.Column("model", sa.String(length=128), nullable=True))
    op.add_column("comp_clusters", sa.Column("year_bucket", sa.SmallInteger(), nullable=True))

    op.alter_column(
        "comp_clusters",
        "generation",
        existing_type=sa.Enum(name="generation_enum"),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_comp_clusters_year_bucket_range",
        "comp_clusters",
        "year_bucket IS NULL OR year_bucket BETWEEN 1886 AND 2100",
    )
    op.create_index(
        "idx_comp_clusters_lookup",
        "comp_clusters",
        ["make", "model", "generation", "year_bucket", "body_style", "transmission"],
        unique=False,
    )

    op.execute(
        """
        UPDATE comp_clusters
        SET make = 'Porsche',
            model = '911',
            year_bucket = NULL,
            cluster_key = lower(
                concat(
                    'porsche:911:',
                    generation::text,
                    ':',
                    body_style::text,
                    ':',
                    transmission::text
                )
            )
        WHERE make IS NULL OR model IS NULL
        """
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


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS active_listings_with_delta")
    op.execute("DELETE FROM comp_clusters")
    op.drop_index("idx_comp_clusters_lookup", table_name="comp_clusters")
    op.drop_constraint("ck_comp_clusters_year_bucket_range", "comp_clusters", type_="check")
    op.alter_column(
        "comp_clusters",
        "generation",
        existing_type=sa.Enum(name="generation_enum"),
        nullable=False,
    )
    op.drop_column("comp_clusters", "year_bucket")
    op.drop_column("comp_clusters", "model")
    op.drop_column("comp_clusters", "make")

    op.execute(
        """
        CREATE VIEW active_listings_with_delta AS
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
            END AS delta_pct
        FROM listings l
        LEFT JOIN comp_clusters cc
            ON cc.generation = l.generation
            AND cc.body_style = l.body_style
            AND cc.transmission = l.transmission
        WHERE l.listing_status = 'active'
        """
    )
