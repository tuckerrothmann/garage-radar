"""generalize_to_multi_make

Migrates the schema from a Porsche 911-only tool to a general-purpose
vintage car intelligence platform.

Changes:
  - Add make, model TEXT columns to listings, comps, comp_clusters
  - Backfill existing rows with make='Porsche', model='911'
  - Drop year BETWEEN 1965 AND 1998 check constraint
  - Convert listings.generation and comps.generation from generation_enum → TEXT
  - Expand body_style_enum with new body style values
  - Add fwd to drivetrain_enum
  - Remove generation column from comp_clusters; add make + model (NOT NULL)
  - Rebuild comp_clusters cluster_key format: 'make:model:body_style:transmission'
  - Drop idx_listings_generation; add idx_listings_make_model
  - Replace idx_comps_generation_body_trans with idx_comps_make_model_body_trans
  - Add make/model to canonical_models; convert generation → TEXT
  - Recreate active_listings_with_delta view to join on make+model

Revision ID: a3f2d1e8c904
Revises: e09629634686
Create Date: 2026-03-23 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3f2d1e8c904'
down_revision: Union[str, Sequence[str], None] = 'e09629634686'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Expand body_style_enum ─────────────────────────────────────────────
    # Postgres ALTER TYPE ADD VALUE is non-transactional; must run outside a
    # transaction block.  Alembic's op.execute() runs inside a transaction by
    # default, so we use the IF NOT EXISTS guard which is safe to re-run.
    for value in ("convertible", "roadster", "fastback", "hardtop", "sedan", "wagon", "pickup"):
        op.execute(f"ALTER TYPE body_style_enum ADD VALUE IF NOT EXISTS '{value}'")

    # ── 2. Expand drivetrain_enum ─────────────────────────────────────────────
    op.execute("ALTER TYPE drivetrain_enum ADD VALUE IF NOT EXISTS 'fwd'")

    # ── 3. Add make + model to listings ──────────────────────────────────────
    op.add_column("listings", sa.Column("make", sa.Text(), nullable=True))
    op.add_column("listings", sa.Column("model", sa.Text(), nullable=True))
    op.execute("UPDATE listings SET make = 'Porsche', model = '911'")

    # ── 4. Drop year range constraint ─────────────────────────────────────────
    op.drop_constraint("ck_listings_year_range", "listings", type_="check")

    # ── 5. Convert listings.generation from enum → text ───────────────────────
    op.execute(
        "ALTER TABLE listings ALTER COLUMN generation TYPE TEXT USING generation::TEXT"
    )

    # ── 6. Drop old generation index; add make+model index ───────────────────
    op.drop_index("idx_listings_generation", table_name="listings")
    op.create_index("idx_listings_make_model", "listings", ["make", "model"])

    # ── 7. Add make + model to comps ──────────────────────────────────────────
    op.add_column("comps", sa.Column("make", sa.Text(), nullable=True))
    op.add_column("comps", sa.Column("model", sa.Text(), nullable=True))
    op.execute("UPDATE comps SET make = 'Porsche', model = '911'")

    # ── 8. Convert comps.generation from enum → text ──────────────────────────
    op.execute(
        "ALTER TABLE comps ALTER COLUMN generation TYPE TEXT USING generation::TEXT"
    )

    # ── 9. Replace comps generation index with make+model index ──────────────
    op.drop_index("idx_comps_generation_body_trans", table_name="comps")
    op.create_index(
        "idx_comps_make_model_body_trans",
        "comps",
        ["make", "model", "body_style", "transmission"],
    )

    # ── 10. Update comp_clusters ──────────────────────────────────────────────
    # Add make + model (nullable first, backfill, then set NOT NULL)
    op.add_column("comp_clusters", sa.Column("make", sa.Text(), nullable=True))
    op.add_column("comp_clusters", sa.Column("model", sa.Text(), nullable=True))
    op.execute("UPDATE comp_clusters SET make = 'Porsche', model = '911'")
    op.alter_column("comp_clusters", "make", nullable=False)
    op.alter_column("comp_clusters", "model", nullable=False)

    # Rebuild cluster_key to new format: 'make:model:body_style:transmission'
    op.execute(
        """
        UPDATE comp_clusters
        SET cluster_key = make || ':' || model || ':' || body_style || ':' || transmission
        """
    )

    # Drop generation column (was NOT NULL, now superseded by make+model)
    op.drop_column("comp_clusters", "generation")

    # ── 11. Update canonical_models ───────────────────────────────────────────
    op.add_column("canonical_models", sa.Column("make", sa.Text(), nullable=True))
    op.add_column("canonical_models", sa.Column("model", sa.Text(), nullable=True))
    op.execute("UPDATE canonical_models SET make = 'Porsche', model = '911'")
    op.execute(
        "ALTER TABLE canonical_models ALTER COLUMN generation TYPE TEXT USING generation::TEXT"
    )

    # ── 12. Drop generation_enum (no longer used) ─────────────────────────────
    # Only safe once all columns referencing it have been converted to TEXT.
    op.execute("DROP TYPE IF EXISTS generation_enum")


def downgrade() -> None:
    # Recreate generation_enum
    op.execute(
        "CREATE TYPE generation_enum AS ENUM ('G1', 'G2', 'G3', 'G4', 'G5', 'G6')"
    )

    # Restore canonical_models
    op.drop_column("canonical_models", "make")
    op.drop_column("canonical_models", "model")
    op.execute(
        """
        ALTER TABLE canonical_models
        ALTER COLUMN generation TYPE generation_enum
        USING generation::generation_enum
        """
    )

    # Restore comp_clusters
    op.add_column(
        "comp_clusters",
        sa.Column(
            "generation",
            sa.Enum("G1", "G2", "G3", "G4", "G5", "G6", name="generation_enum"),
            nullable=True,
        ),
    )
    # Attempt to recover generation from cluster_key (first segment)
    op.execute(
        """
        UPDATE comp_clusters
        SET generation = split_part(cluster_key, ':', 1)::generation_enum
        WHERE split_part(cluster_key, ':', 1) IN ('G1','G2','G3','G4','G5','G6')
        """
    )
    op.drop_column("comp_clusters", "make")
    op.drop_column("comp_clusters", "model")

    # Restore comps
    op.drop_index("idx_comps_make_model_body_trans", table_name="comps")
    op.create_index(
        "idx_comps_generation_body_trans",
        "comps",
        ["generation", "body_style", "transmission"],
    )
    op.execute(
        """
        ALTER TABLE comps
        ALTER COLUMN generation TYPE generation_enum
        USING generation::generation_enum
        """
    )
    op.drop_column("comps", "make")
    op.drop_column("comps", "model")

    # Restore listings
    op.drop_index("idx_listings_make_model", table_name="listings")
    op.create_index("idx_listings_generation", "listings", ["generation"])
    op.execute(
        """
        ALTER TABLE listings
        ALTER COLUMN generation TYPE generation_enum
        USING generation::generation_enum
        """
    )
    op.create_check_constraint(
        "ck_listings_year_range", "listings", "year BETWEEN 1965 AND 1998"
    )
    op.drop_column("listings", "make")
    op.drop_column("listings", "model")
