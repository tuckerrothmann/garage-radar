#!/usr/bin/env python3
"""Load fixture data into the DB for local dev/testing."""
import asyncio
import json
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/garage_radar"


async def main():
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    fixtures_dir = Path(__file__).parent.parent / "data" / "fixtures"

    # ── Load comps ─────────────────────────────────────────────────────────
    comps_path = fixtures_dir / "sample_comps.json"
    with open(comps_path) as f:
        data = json.load(f)

    comps = data["comps"]
    print(f"Loading {len(comps)} comps from fixture...")

    async with session_factory() as session:
        for comp in comps:
            row_id = str(uuid.uuid4())
            sale_date = date.fromisoformat(comp["sale_date"]) if comp.get("sale_date") else None

            await session.execute(text("""
                INSERT INTO comps (
                    id, source, source_url, year, generation, body_style, trim,
                    transmission, engine_variant, exterior_color_canonical,
                    exterior_color_raw, mileage, sale_price, sale_date,
                    price_type, currency, bidder_count, matching_numbers,
                    original_paint, service_history, confidence_score, notes,
                    make, model
                ) VALUES (
                    :id, :source, :source_url, :year, :generation, :body_style, :trim,
                    :transmission, :engine_variant, :exterior_color_canonical,
                    :exterior_color_raw, :mileage, :sale_price, :sale_date,
                    :price_type, :currency, :bidder_count, :matching_numbers,
                    :original_paint, :service_history, :confidence_score, :notes,
                    :make, :model
                )
                ON CONFLICT (source, source_url) DO NOTHING
            """), {
                "id": row_id,
                "source": comp["source"],
                "source_url": comp["source_url"],
                "year": comp["year"],
                "generation": comp.get("generation"),
                "body_style": comp.get("body_style"),
                "trim": comp.get("trim"),
                "transmission": comp.get("transmission"),
                "engine_variant": comp.get("engine_variant"),
                "exterior_color_canonical": comp.get("exterior_color_canonical"),
                "exterior_color_raw": None,
                "mileage": comp.get("mileage"),
                "sale_price": comp.get("sale_price"),
                "sale_date": sale_date,
                "price_type": comp.get("price_type", "auction_final"),
                "currency": comp.get("currency", "USD"),
                "bidder_count": comp.get("bidder_count"),
                "matching_numbers": comp.get("matching_numbers"),
                "original_paint": comp.get("original_paint"),
                "service_history": comp.get("service_history"),
                "confidence_score": comp.get("confidence_score"),
                "notes": comp.get("notes"),
                "make": "Porsche",
                "model": "911",
            })

        await session.commit()
        print(f"✅ Comps loaded.")

    # ── Load active listing ────────────────────────────────────────────────
    listing_path = fixtures_dir / "sample_listing_bat.json"
    with open(listing_path) as f:
        listing = json.load(f)

    print("Loading 1 active listing from fixture...")
    async with session_factory() as session:
        scrape_ts = datetime.fromisoformat(listing["scrape_ts"].replace("Z", "+00:00"))
        listing_date = date.fromisoformat(listing["listing_date"])

        await session.execute(text("""
            INSERT INTO listings (
                id, source, source_url, scrape_ts, listing_status,
                year, generation, body_style, trim, drivetrain,
                engine_variant, transmission,
                exterior_color_raw, exterior_color_canonical, interior_color_raw,
                mileage, vin, title_status, asking_price, currency,
                price_history, final_price,
                matching_numbers, original_paint, service_history,
                modification_flags, normalization_confidence,
                description_raw, listing_date, seller_type, location,
                bidder_count, title_raw, make, model
            ) VALUES (
                :id, :source, :source_url, :scrape_ts, :listing_status,
                :year, :generation, :body_style, :trim, :drivetrain,
                :engine_variant, :transmission,
                :exterior_color_raw, :exterior_color_canonical, :interior_color_raw,
                :mileage, :vin, :title_status, :asking_price, :currency,
                :price_history, :final_price,
                :matching_numbers, :original_paint, :service_history,
                :modification_flags, :normalization_confidence,
                :description_raw, :listing_date, :seller_type, :location,
                :bidder_count, :title_raw, :make, :model
            )
            ON CONFLICT (source, source_url) DO NOTHING
        """), {
            "id": str(uuid.uuid4()),
            "source": listing["source"],
            "source_url": listing["source_url"],
            "scrape_ts": scrape_ts,
            "listing_status": listing["listing_status"],
            "year": listing["year"],
            "generation": listing.get("generation"),
            "body_style": listing.get("body_style"),
            "trim": listing.get("trim"),
            "drivetrain": listing.get("drivetrain", "rwd"),
            "engine_variant": listing.get("engine_variant"),
            "transmission": listing.get("transmission"),
            "exterior_color_raw": listing.get("exterior_color_raw"),
            "exterior_color_canonical": listing.get("exterior_color_canonical"),
            "interior_color_raw": listing.get("interior_color_raw"),
            "mileage": listing.get("mileage"),
            "vin": listing.get("vin"),
            "title_status": listing.get("title_status", "unknown"),
            "asking_price": listing.get("asking_price"),
            "currency": listing.get("currency", "USD"),
            "price_history": json.dumps(listing.get("price_history", [])),
            "final_price": listing.get("final_price"),
            "matching_numbers": listing.get("matching_numbers"),
            "original_paint": listing.get("original_paint"),
            "service_history": listing.get("service_history"),
            "modification_flags": listing.get("modification_flags", []),
            "normalization_confidence": listing.get("normalization_confidence"),
            "description_raw": listing.get("description_raw"),
            "listing_date": listing_date,
            "seller_type": listing.get("seller_type"),
            "location": listing.get("location"),
            "bidder_count": listing.get("bidder_count"),
            "title_raw": None,
            "make": "Porsche",
            "model": "911",
        })
        await session.commit()
        print("✅ Active listing loaded.")

    await engine.dispose()
    print("\nDone! DB now has fixture data ready for the insight engine.")


if __name__ == "__main__":
    asyncio.run(main())
