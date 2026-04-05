"""
API unit tests — no live database required.

Uses FastAPI's TestClient (sync) after overriding the DB dependency with a
mock session. Tests verify:
  - Schema serialisation and HTTP status codes
  - Filter validation (bad enum → 400)
  - Alert status transition logic (valid and invalid transitions)
  - Health endpoint

Run: pytest backend/tests/test_api.py -v
"""
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from garage_radar.api import app
from garage_radar.api.deps import get_db
from garage_radar.db.models import (
    Alert,
    AlertSeverityEnum,
    AlertStatusEnum,
    AlertTypeEnum,
    BodyStyleEnum,
    CompCluster,
    CurrencyEnum,
    DrivetrainEnum,
    GenerationEnum,
    Listing,
    ListingStatusEnum,
    SourceEnum,
    TitleStatusEnum,
    TransmissionEnum,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _listing(**kwargs) -> Listing:
    defaults = {
        "id": uuid.uuid4(),
        "source": SourceEnum.bat,
        "source_url": "https://bringatrailer.com/listing/test/",
        "listing_status": ListingStatusEnum.active,
        "year": 1995,
        "make": "Porsche",
        "model": "911",
        "generation": GenerationEnum.G6,
        "body_style": BodyStyleEnum.coupe,
        "trim": None,
        "drivetrain": DrivetrainEnum.rwd,
        "transmission": TransmissionEnum.manual,
        "engine_variant": None,
        "exterior_color_canonical": None,
        "exterior_color_raw": None,
        "interior_color_raw": None,
        "mileage": None,
        "vin": None,
        "title_status": TitleStatusEnum.clean,
        "current_bid": None,
        "asking_price": 85000.0,
        "currency": CurrencyEnum.USD,
        "final_price": None,
        "price_history": [],
        "matching_numbers": None,
        "original_paint": None,
        "service_history": None,
        "modification_flags": None,
        "normalization_confidence": None,
        "listing_date": None,
        "auction_end_at": None,
        "time_remaining_text": None,
        "seller_type": None,
        "seller_name": None,
        "location": None,
        "bidder_count": None,
        "title_raw": None,
        "description_raw": None,
        "scrape_ts": datetime.now(UTC),
        "snapshot_path": None,
        "possible_duplicate_id": None,
        "alerts": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    obj = MagicMock(spec=Listing)
    for k, v in defaults.items():
        setattr(obj, k, v)
    # Allow table column iteration for _enrich()
    obj.__table__ = Listing.__table__
    return obj


def _alert(**kwargs) -> Alert:
    defaults = {
        "id": uuid.uuid4(),
        "alert_type": AlertTypeEnum.new_listing,
        "triggered_at": datetime.now(UTC),
        "listing_id": uuid.uuid4(),
        "reason": "Test alert",
        "delta_pct": None,
        "severity": AlertSeverityEnum.info,
        "status": AlertStatusEnum.open,
        "notified_at": None,
    }
    defaults.update(kwargs)
    obj = MagicMock(spec=Alert)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _cluster(**kwargs) -> CompCluster:
    defaults = {
        "id": 1,
        "cluster_key": "porsche:911:g6:coupe:manual:usd",
        "make": "Porsche",
        "model": "911",
        "generation": GenerationEnum.G6,
        "year_bucket": None,
        "body_style": BodyStyleEnum.coupe,
        "transmission": TransmissionEnum.manual,
        "currency": CurrencyEnum.USD,
        "window_days": 90,
        "comp_count": 5,
        "median_price": 80000.0,
        "p25_price": 75000.0,
        "p75_price": 85000.0,
        "min_price": 70000.0,
        "max_price": 90000.0,
        "avg_confidence": 0.9,
        "insufficient_data": False,
        "last_computed_at": datetime.now(UTC),
    }
    defaults.update(kwargs)
    obj = MagicMock(spec=CompCluster)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _mock_session(scalar_return=None, scalars_return=None, execute_return=None):
    """Build a minimal async mock session."""
    session = AsyncMock()
    if scalar_return is not None:
        session.scalar = AsyncMock(return_value=scalar_return)
    if scalars_return is not None:
        result = MagicMock()
        result.scalars.return_value.all.return_value = scalars_return
        session.execute = AsyncMock(return_value=result)
    if execute_return is not None:
        session.execute = AsyncMock(return_value=execute_return)
    return session


def _override_db(session):
    """Return a dependency override that yields the given session."""
    async def _dep():
        yield session
    return _dep


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self):
        client = TestClient(app)
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


# ── Listings ──────────────────────────────────────────────────────────────────

class TestListingsEndpoint:
    def _client(self, listings: list, total: int = None, clusters: list | None = None):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=total or len(listings))

        listing_result = MagicMock()
        listing_result.scalars.return_value.all.return_value = listings

        cluster_result = MagicMock()
        cluster_result.scalars.return_value.all.return_value = clusters or []

        execute_side_effect = [listing_result]
        if listings:
            execute_side_effect.append(cluster_result)

        session.execute = AsyncMock(side_effect=execute_side_effect)
        app.dependency_overrides[get_db] = _override_db(session)
        return TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_empty_returns_page(self):
        client = self._client([])
        r = client.get("/listings")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []
        assert body["limit"] == 50
        assert body["offset"] == 0

    def test_listing_in_response(self):
        listing = _listing(
            current_bid=61000.0,
            auction_end_at=datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
            time_remaining_text="3 days",
        )
        client = self._client([listing])
        r = client.get("/listings")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["year"] == 1995
        assert items[0]["make"] == "Porsche"
        assert items[0]["model"] == "911"
        assert items[0]["generation"] == "G6"
        assert items[0]["source"] == "bat"
        assert items[0]["current_bid"] == 61000.0
        assert items[0]["time_remaining_text"] == "3 days"

    def test_invalid_generation_returns_400(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=0)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)
        app.dependency_overrides[get_db] = _override_db(session)
        client = TestClient(app)
        r = client.get("/listings?generation=INVALID")
        assert r.status_code == 400

    def test_invalid_status_returns_400(self):
        session = AsyncMock()
        app.dependency_overrides[get_db] = _override_db(session)
        client = TestClient(app)
        r = client.get("/listings?status=flying")
        assert r.status_code == 400

    def test_pagination_params_reflected(self):
        client = self._client([])
        r = client.get("/listings?limit=10&offset=20")
        assert r.status_code == 200
        body = r.json()
        assert body["limit"] == 10
        assert body["offset"] == 20

    def test_limit_max_enforced(self):
        session = AsyncMock()
        app.dependency_overrides[get_db] = _override_db(session)
        client = TestClient(app)
        r = client.get("/listings?limit=999")
        # FastAPI validates Query(le=200) and returns 422
        assert r.status_code == 422

    def test_delta_pct_none_when_no_cluster(self):
        listing = _listing(asking_price=85000.0)
        client = self._client([listing])
        r = client.get("/listings")
        item = r.json()["items"][0]
        assert item["delta_pct"] is None
        assert item["cluster_median"] is None

    def test_non_porsche_listing_uses_year_bucket_cluster(self):
        listing = _listing(
            year=1972,
            make="Ford",
            model="Bronco",
            generation=None,
            body_style=BodyStyleEnum.suv,
            transmission=TransmissionEnum.manual,
            asking_price=50000.0,
        )
        cluster = _cluster(
            cluster_key="ford:bronco:y1972:suv:manual:usd",
            make="Ford",
            model="Bronco",
            generation=None,
            year_bucket=1972,
            body_style=BodyStyleEnum.suv,
            transmission=TransmissionEnum.manual,
            median_price=40000.0,
        )
        client = self._client([listing], clusters=[cluster])
        r = client.get("/listings")
        item = r.json()["items"][0]
        assert item["cluster_median"] == 40000.0
        assert item["cluster_comp_count"] == 5
        assert item["cluster_p25"] == 75000.0
        assert item["cluster_p75"] == 85000.0
        assert item["cluster_window_days"] == 90
        assert item["delta_pct"] == 25.0

    def test_multi_value_filters_are_accepted(self):
        client = self._client([])
        r = client.get("/listings?make=Ford&make=BMW&year=1972&year=1974&status=active&status=sold")
        assert r.status_code == 200

    def test_cluster_lookup_is_batched_for_page(self):
        listing_a = _listing()
        listing_b = _listing(
            id=uuid.uuid4(),
            year=1972,
            make="Ford",
            model="Bronco",
            generation=None,
            body_style=BodyStyleEnum.suv,
            transmission=TransmissionEnum.manual,
            asking_price=50000.0,
        )
        cluster_a = _cluster()
        cluster_b = _cluster(
            cluster_key="ford:bronco:y1972:suv:manual:usd",
            make="Ford",
            model="Bronco",
            generation=None,
            year_bucket=1972,
            body_style=BodyStyleEnum.suv,
            transmission=TransmissionEnum.manual,
            median_price=40000.0,
        )

        session = AsyncMock()
        session.scalar = AsyncMock(return_value=2)

        listing_result = MagicMock()
        listing_result.scalars.return_value.all.return_value = [listing_a, listing_b]

        cluster_result = MagicMock()
        cluster_result.scalars.return_value.all.return_value = [cluster_a, cluster_b]

        session.execute = AsyncMock(side_effect=[listing_result, cluster_result])
        app.dependency_overrides[get_db] = _override_db(session)
        client = TestClient(app)

        r = client.get("/listings")

        assert r.status_code == 200
        assert session.scalar.await_count == 1
        assert session.execute.await_count == 2


class TestListingDetailEndpoint:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_not_found_returns_404(self):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)
        app.dependency_overrides[get_db] = _override_db(session)
        client = TestClient(app)
        r = client.get(f"/listings/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_found_returns_listing(self):
        listing = _listing()
        session = AsyncMock()
        # scalar: listing, then cluster (None)
        session.scalar = AsyncMock(side_effect=[listing, None])
        app.dependency_overrides[get_db] = _override_db(session)
        client = TestClient(app)
        r = client.get(f"/listings/{listing.id}")
        assert r.status_code == 200
        assert r.json()["id"] == str(listing.id)


# ── Comps ─────────────────────────────────────────────────────────────────────

class TestCompsEndpoint:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def _client(self, comps=None, total=0):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=total)
        result = MagicMock()
        result.scalars.return_value.all.return_value = comps or []
        session.execute = AsyncMock(return_value=result)
        app.dependency_overrides[get_db] = _override_db(session)
        return TestClient(app)

    def test_empty_comps(self):
        client = self._client()
        r = client.get("/comps")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_invalid_generation_400(self):
        client = self._client()
        r = client.get("/comps?generation=Z9")
        assert r.status_code == 400

    def test_invalid_source_400(self):
        client = self._client()
        r = client.get("/comps?source=craigslist")
        assert r.status_code == 400


class TestCompClustersEndpoint:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def _client(self, clusters=None):
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = clusters or []
        session.execute = AsyncMock(return_value=result)
        app.dependency_overrides[get_db] = _override_db(session)
        return TestClient(app)

    def test_empty_clusters(self):
        client = self._client()
        r = client.get("/comps/clusters")
        assert r.status_code == 200
        assert r.json() == []

    def test_invalid_transmission_400(self):
        client = self._client()
        r = client.get("/comps/clusters?transmission=cvt")
        assert r.status_code == 400

    def test_cluster_response_includes_make_model_and_year_bucket(self):
        client = self._client(
            [
                _cluster(
                    cluster_key="ford:bronco:y1972:suv:manual:usd",
                    make="Ford",
                    model="Bronco",
                    generation=None,
                    year_bucket=1972,
                    body_style=BodyStyleEnum.suv,
                    transmission=TransmissionEnum.manual,
                )
            ]
        )
        r = client.get("/comps/clusters")
        assert r.status_code == 200
        item = r.json()[0]
        assert item["make"] == "Ford"
        assert item["model"] == "Bronco"
        assert item["generation"] is None
        assert item["year_bucket"] == 1972
        assert item["currency"] == "USD"


class TestVehicleProfileEndpoint:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_vehicle_profile_response(self):
        session = AsyncMock()
        app.dependency_overrides[get_db] = _override_db(session)
        client = TestClient(app)

        payload = {
            "make": "Ford",
            "model": "Bronco",
            "year": 1972,
            "slug": "ford:bronco",
            "display_name": "Ford Bronco",
            "profile_source": "curated+external",
            "overview": "Test overview",
            "canonical_url": "https://en.wikipedia.org/wiki/Ford_Bronco",
            "hero_image_url": "https://upload.wikimedia.org/example.jpg",
            "production_years": "1966-present",
            "body_styles": ["suv"],
            "transmissions": ["manual", "auto"],
            "notable_trims": ["U15 Wagon"],
            "encyclopedia_facts": {"Manufacturer": "Ford", "Known for": "Body-on-frame SUVs"},
            "market_facts": {"Observed years": "1968-1976", "Garage Radar coverage": "Early market coverage"},
            "quick_facts": {"Manufacturer": "Ford"},
            "highlights": ["Body style matters."],
            "common_questions": ["Is it rust free?"],
            "buying_tips": ["Check documentation."],
            "market_summary": "Tracked locally.",
            "market_signals": ["Asks are close to recent sales."],
            "recent_sales_scope": "Ford Bronco",
            "local_observations": ["Coverage spans multiple years."],
            "reference_links": [
                {
                    "name": "Wikipedia",
                    "url": "https://en.wikipedia.org/wiki/Ford_Bronco",
                    "license": "CC BY-SA 4.0",
                }
            ],
            "external_sections": [
                {
                    "title": "History",
                    "summary": "Bronco history summary.",
                    "source_name": "Wikipedia",
                    "source_url": "https://en.wikipedia.org/wiki/Ford_Bronco#History",
                }
            ],
            "related_model_breakdown": [{"label": "Bronco Ranger", "count": 2}],
            "body_style_breakdown": [{"label": "suv", "count": 4}],
            "recent_sales": [
                {
                    "id": str(uuid.uuid4()),
                    "title": "1972 Ford Bronco U15",
                    "source": "bat",
                    "source_url": "https://bringatrailer.com/listing/test-bronco/",
                    "year": 1972,
                    "sale_price": 62000,
                    "currency": "USD",
                    "sale_date": "2026-03-01",
                }
            ],
            "stats": {
                "listing_count": 4,
                "comp_count": 1,
                "year_min": 1968,
                "year_max": 1976,
                "avg_asking_price": 65000,
                "min_asking_price": 50000,
                "max_asking_price": 90000,
                "avg_sale_price": 62000,
                "min_sale_price": 62000,
                "max_sale_price": 62000,
                "latest_listing_at": "2026-03-25T12:00:00Z",
                "latest_sale_date": "2026-03-01",
                "sources": ["bat"],
            },
            "transmission_breakdown": [{"label": "manual", "count": 3}],
            "trim_breakdown": [{"label": "U15 Wagon", "count": 2}],
        }

        with patch(
            "garage_radar.api.routers.vehicles.build_vehicle_profile",
            new=AsyncMock(return_value=payload),
        ):
            r = client.get("/vehicles/profile?make=Ford&model=Bronco&year=1972")

        assert r.status_code == 200
        body = r.json()
        assert body["slug"] == "ford:bronco"
        assert body["display_name"] == "Ford Bronco"
        assert body["canonical_url"] == "https://en.wikipedia.org/wiki/Ford_Bronco"
        assert body["reference_links"][0]["name"] == "Wikipedia"
        assert body["external_sections"][0]["title"] == "History"
        assert body["market_signals"][0] == "Asks are close to recent sales."
        assert body["related_model_breakdown"][0]["label"] == "Bronco Ranger"
        assert body["recent_sales"][0]["sale_price"] == 62000
        assert body["stats"]["listing_count"] == 4


# ── Alerts ────────────────────────────────────────────────────────────────────

class TestAlertsEndpoint:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def _client(self, alerts=None, total=0):
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=total)
        result = MagicMock()
        result.scalars.return_value.all.return_value = alerts or []
        session.execute = AsyncMock(return_value=result)
        app.dependency_overrides[get_db] = _override_db(session)
        return TestClient(app)

    def test_default_returns_open_alerts(self):
        client = self._client()
        r = client.get("/alerts")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_invalid_status_400(self):
        client = self._client()
        r = client.get("/alerts?status=maybe")
        assert r.status_code == 400

    def test_invalid_severity_400(self):
        client = self._client()
        r = client.get("/alerts?severity=critical")
        assert r.status_code == 400

    def test_invalid_alert_type_400(self):
        client = self._client()
        r = client.get("/alerts?alert_type=unicorn")
        assert r.status_code == 400

    def test_alert_in_response(self):
        alert = _alert()
        client = self._client([alert], total=1)
        r = client.get("/alerts")
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["alert_type"] == "new_listing"
        assert items[0]["status"] == "open"


class TestAlertStatusPatch:
    def teardown_method(self):
        app.dependency_overrides.clear()

    def _client_with_alert(self, alert):
        session = AsyncMock()
        session.get = AsyncMock(return_value=alert)
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        app.dependency_overrides[get_db] = _override_db(session)
        return TestClient(app)

    def test_open_to_read_allowed(self):
        alert = _alert(status=AlertStatusEnum.open)
        client = self._client_with_alert(alert)
        r = client.patch(f"/alerts/{alert.id}/status", json={"status": "read"})
        assert r.status_code == 200

    def test_open_to_dismissed_allowed(self):
        alert = _alert(status=AlertStatusEnum.open)
        client = self._client_with_alert(alert)
        r = client.patch(f"/alerts/{alert.id}/status", json={"status": "dismissed"})
        assert r.status_code == 200

    def test_read_to_dismissed_allowed(self):
        alert = _alert(status=AlertStatusEnum.read)
        client = self._client_with_alert(alert)
        r = client.patch(f"/alerts/{alert.id}/status", json={"status": "dismissed"})
        assert r.status_code == 200

    def test_dismissed_to_open_rejected(self):
        alert = _alert(status=AlertStatusEnum.dismissed)
        client = self._client_with_alert(alert)
        r = client.patch(f"/alerts/{alert.id}/status", json={"status": "open"})
        assert r.status_code == 422

    def test_read_to_open_rejected(self):
        alert = _alert(status=AlertStatusEnum.read)
        client = self._client_with_alert(alert)
        r = client.patch(f"/alerts/{alert.id}/status", json={"status": "open"})
        assert r.status_code == 422

    def test_invalid_status_value_rejected(self):
        alert = _alert(status=AlertStatusEnum.open)
        client = self._client_with_alert(alert)
        r = client.patch(f"/alerts/{alert.id}/status", json={"status": "archived"})
        assert r.status_code == 400

    def test_alert_not_found_404(self):
        session = AsyncMock()
        session.get = AsyncMock(return_value=None)
        app.dependency_overrides[get_db] = _override_db(session)
        client = TestClient(app)
        r = client.patch(f"/alerts/{uuid.uuid4()}/status", json={"status": "read"})
        assert r.status_code == 404
