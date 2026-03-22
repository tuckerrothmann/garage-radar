#!/usr/bin/env python3
"""
Bootstrap the Garage Radar database with reference seed data.
Runs after `alembic upgrade head`.

Usage:
    python scripts/bootstrap_db.py
    # or via Makefile:
    make seed
"""
import sys
from pathlib import Path

# Add backend to path so we can import garage_radar
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import json
import psycopg2
from garage_radar.config import get_settings

GENERATION_TABLE_PATH = Path(__file__).parent.parent / "normalize" / "generation_table.json"


def main():
    settings = get_settings()
    print(f"Connecting to: {settings.database_url}")

    conn = psycopg2.connect(settings.database_url)
    cur = conn.cursor()

    # Load generation table
    with open(GENERATION_TABLE_PATH) as f:
        gen_table = json.load(f)

    generations = gen_table["generations"]

    generation_meta = {
        "G1": {
            "known_trims": ["911", "911T", "911E", "911S", "912", "2.7RS", "Carrera RS"],
            "known_engine_variants": ["2.0", "2.2", "2.4", "2.7"],
            "comp_weight": 1.0,
        },
        "G2": {
            "known_trims": ["Carrera", "911S", "Turbo", "930"],
            "known_engine_variants": ["2.7", "3.0", "3.0T"],
            "comp_weight": 1.0,
        },
        "G3": {
            "known_trims": ["SC", "SC Targa", "SC Cabriolet", "Turbo", "930"],
            "known_engine_variants": ["3.0", "3.3T"],
            "comp_weight": 1.0,
        },
        "G4": {
            "known_trims": ["Carrera", "Carrera Targa", "Carrera Cabriolet", "Speedster", "Turbo"],
            "known_engine_variants": ["3.2", "3.3T"],
            "comp_weight": 1.0,
        },
        "G5": {
            "known_trims": ["Carrera 2", "Carrera 4", "Targa", "Cabriolet", "Turbo 3.3", "Turbo 3.6", "RS America"],
            "known_engine_variants": ["3.6", "3.3T", "3.6T"],
            "comp_weight": 1.0,
        },
        "G6": {
            "known_trims": ["Carrera", "Carrera 4", "Targa", "Cabriolet", "Turbo", "Turbo S", "Carrera RS", "GT2"],
            "known_engine_variants": ["3.6", "3.6T", "3.8T"],
            "comp_weight": 1.2,
        },
    }

    inserted = 0
    for gen_code, meta in generations.items():
        extra = generation_meta.get(gen_code, {})
        cur.execute(
            """
            INSERT INTO canonical_models
                (generation, years_start, years_end, common_name,
                 known_trims, known_engine_variants, comp_weight, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                gen_code,
                meta["years_start"],
                meta["years_end"],
                meta["label"],
                extra.get("known_trims", []),
                extra.get("known_engine_variants", []),
                extra.get("comp_weight", 1.0),
                meta.get("notes", ""),
            )
        )
        inserted += cur.rowcount

    conn.commit()
    cur.close()
    conn.close()

    print(f"✅ Seeded {inserted} canonical model records.")
    print("   (0 inserted = records already exist, which is fine)")


if __name__ == "__main__":
    main()
