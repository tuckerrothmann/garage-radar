"""generalize vehicle identity

Revision ID: 7d4a8c2b1f70
Revises: e09629634686
Create Date: 2026-03-25 22:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7d4a8c2b1f70"
down_revision = "e09629634686"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("make", sa.String(length=64), nullable=True))
    op.add_column("listings", sa.Column("model", sa.String(length=128), nullable=True))
    op.add_column("comps", sa.Column("make", sa.String(length=64), nullable=True))
    op.add_column("comps", sa.Column("model", sa.String(length=128), nullable=True))

    op.create_index("idx_listings_make", "listings", ["make"], unique=False)
    op.create_index("idx_listings_make_model", "listings", ["make", "model"], unique=False)
    op.create_index("idx_comps_make_model", "comps", ["make", "model"], unique=False)

    op.drop_constraint("ck_listings_year_range", "listings", type_="check")
    op.create_check_constraint("ck_listings_year_range", "listings", "year BETWEEN 1886 AND 2100")
    op.create_check_constraint("ck_comps_year_range", "comps", "year BETWEEN 1886 AND 2100")

    op.execute(
        """
        UPDATE listings
        SET make = COALESCE(make, 'Porsche'),
            model = COALESCE(
                model,
                CASE
                    WHEN title_raw ILIKE '%Porsche 912%' THEN '912'
                    ELSE '911'
                END
            )
        WHERE make IS NULL
          AND (
                generation IS NOT NULL
                OR title_raw ILIKE '%Porsche 911%'
                OR title_raw ILIKE '%Porsche 912%'
          )
        """
    )
    op.execute(
        """
        UPDATE comps
        SET make = COALESCE(make, 'Porsche'),
            model = COALESCE(
                model,
                CASE
                    WHEN trim ILIKE '%912%' THEN '912'
                    ELSE '911'
                END
            )
        WHERE make IS NULL
          AND generation IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint("ck_comps_year_range", "comps", type_="check")
    op.drop_constraint("ck_listings_year_range", "listings", type_="check")
    op.create_check_constraint("ck_listings_year_range", "listings", "year BETWEEN 1965 AND 1998")

    op.drop_index("idx_comps_make_model", table_name="comps")
    op.drop_index("idx_listings_make_model", table_name="listings")
    op.drop_index("idx_listings_make", table_name="listings")

    op.drop_column("comps", "model")
    op.drop_column("comps", "make")
    op.drop_column("listings", "model")
    op.drop_column("listings", "make")
