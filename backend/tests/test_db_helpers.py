from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from garage_radar.db import ensure_schema_ready
from garage_radar.db.models import Comp, CurrencyEnum, Listing, PriceTypeEnum, SourceEnum
from garage_radar.db.upsert import mark_listing_removed, upsert_comp, upsert_listing


def _existing_comp() -> Comp:
    return Comp(
        source=SourceEnum.bat,
        source_url="https://bringatrailer.com/listing/test-comp/",
        year=1995,
        make="Porsche",
        model="911",
        sale_price=80000.0,
        sale_date=date(2026, 3, 1),
        trim="Carrera",
        price_type=PriceTypeEnum.auction_final,
        currency=CurrencyEnum.USD,
        confidence_score=0.4,
    )


def _existing_listing() -> Listing:
    return Listing(
        source=SourceEnum.bat,
        source_url="https://bringatrailer.com/listing/test-listing/",
        year=1995,
        make="Porsche",
        model="911",
        asking_price=80000.0,
        currency=CurrencyEnum.USD,
    )


def _engine_with_connection(connection: AsyncMock) -> MagicMock:
    connect_ctx = AsyncMock()
    connect_ctx.__aenter__.return_value = connection
    connect_ctx.__aexit__.return_value = False

    engine = MagicMock()
    engine.connect.return_value = connect_ctx
    return engine


class TestEnsureSchemaReady:
    @pytest.mark.asyncio
    async def test_executes_schema_readiness_query(self):
        connection = AsyncMock()
        engine = _engine_with_connection(connection)

        with patch("garage_radar.db.get_engine", return_value=engine):
            await ensure_schema_ready()

        connection.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_helpful_error_when_schema_is_not_ready(self):
        connection = AsyncMock()
        connection.execute.side_effect = RuntimeError("missing relation")
        engine = _engine_with_connection(connection)

        with (
            patch("garage_radar.db.get_engine", return_value=engine),
            pytest.raises(RuntimeError, match="Database schema is not ready"),
        ):
            await ensure_schema_ready()


class TestUpsertComp:
    @pytest.mark.asyncio
    async def test_existing_comp_is_refreshed_with_new_normalized_fields(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=_existing_comp())
        session.add = MagicMock()

        normalized = {
            "source": SourceEnum.bat,
            "source_url": "https://bringatrailer.com/listing/test-comp/",
            "year": 1995,
            "make": "Porsche",
            "model": "911",
            "sale_price": 86500.0,
            "sale_date": date(2026, 3, 28),
            "trim": "Carrera 4",
            "confidence_score": 0.95,
            "price_type": PriceTypeEnum.auction_final,
            "currency": CurrencyEnum.USD,
        }

        action, comp = await upsert_comp(session, normalized)

        assert action == "updated"
        assert comp is not None
        assert comp.sale_price == 86500.0
        assert comp.sale_date == date(2026, 3, 28)
        assert comp.trim == "Carrera 4"
        assert comp.confidence_score == 0.95
        session.add.assert_called_once_with(comp)

    @pytest.mark.asyncio
    async def test_existing_comp_invalidates_vehicle_profile_cache(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=_existing_comp())
        session.add = MagicMock()

        normalized = {
            "source": SourceEnum.bat,
            "source_url": "https://bringatrailer.com/listing/test-comp/",
            "year": 1995,
            "make": "Porsche",
            "model": "911",
            "sale_price": 86500.0,
            "sale_date": date(2026, 3, 28),
            "price_type": PriceTypeEnum.auction_final,
            "currency": CurrencyEnum.USD,
        }

        with patch("garage_radar.db.upsert._invalidate_vehicle_profile_caches") as invalidate:
            await upsert_comp(session, normalized)

        invalidate.assert_called_once_with(("Porsche", "911"), ("Porsche", "911"))


class TestUpsertListing:
    @pytest.mark.asyncio
    async def test_existing_listing_invalidates_old_and_new_vehicle_profile_cache(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=_existing_listing())
        session.add = MagicMock()

        normalized = {
            "source": SourceEnum.bat,
            "source_url": "https://bringatrailer.com/listing/test-listing/",
            "year": 1995,
            "make": "Porsche",
            "model": "964 Turbo",
            "asking_price": 86500.0,
            "currency": CurrencyEnum.USD,
        }

        with patch("garage_radar.db.upsert._invalidate_vehicle_profile_caches") as invalidate:
            action, listing = await upsert_listing(session, normalized)

        assert action == "updated"
        assert listing is not None
        assert listing.model == "964 Turbo"
        invalidate.assert_called_once_with(("Porsche", "911"), ("Porsche", "964 Turbo"))

    @pytest.mark.asyncio
    async def test_mark_listing_removed_invalidates_vehicle_profile_cache(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=_existing_listing())
        session.add = MagicMock()

        with patch("garage_radar.db.upsert._invalidate_vehicle_profile_caches") as invalidate:
            await mark_listing_removed(
                session,
                source="bat",
                source_url="https://bringatrailer.com/listing/test-listing/",
            )

        invalidate.assert_called_once_with(("Porsche", "911"))
