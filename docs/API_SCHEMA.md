# Garage Radar — API Schema Reference

FastAPI app served at `http://localhost:8000`. Interactive docs at `/docs` (Swagger) and `/redoc`.

---

## Base URL

```
http://localhost:8000/api/v1
```

---

## Endpoints

### GET `/listings`

Returns active listings with ask-vs-comp delta computed.

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `generation` | string | all | Filter by gen code: `G1`–`G6` |
| `body_style` | string | all | `coupe`, `targa`, `cabriolet`, `speedster` |
| `transmission` | string | all | `manual`, `manual-6sp`, `auto` |
| `source` | string | all | `bat`, `carsandbids`, `pcarmarket` |
| `min_year` | int | 1965 | Filter by model year |
| `max_year` | int | 1998 | |
| `max_mileage` | int | — | |
| `underpriced_only` | bool | false | Only return listings with delta_pct ≤ -10% |
| `min_confidence` | float | 0.0 | Minimum normalization_confidence |
| `limit` | int | 50 | Max results (max: 200) |
| `offset` | int | 0 | Pagination offset |

**Response: 200 OK**

```json
{
  "total": 14,
  "listings": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "source": "bat",
      "source_url": "https://bringatrailer.com/listing/...",
      "year": 1995,
      "generation": "G6",
      "body_style": "coupe",
      "trim": "Carrera",
      "transmission": "manual",
      "exterior_color_canonical": "blue-metallic",
      "mileage": 68200,
      "asking_price": 97500,
      "listing_date": "2025-03-14",
      "matching_numbers": true,
      "original_paint": true,
      "service_history": true,
      "modification_flags": [],
      "normalization_confidence": 0.92,
      "cluster_median": 98500,
      "cluster_p25": 87000,
      "cluster_p75": 104000,
      "comp_count": 5,
      "insufficient_data": false,
      "ask_vs_median_pct": -1.0,
      "days_on_market": 1
    }
  ]
}
```

---

### GET `/listings/{id}`

Returns a single listing by UUID.

**Response: 200 OK** — full listing object including `description_raw`, `price_history`, `snapshot_path`.

**Response: 404 Not Found** if ID not found.

---

### GET `/comps`

Returns completed sale comps.

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `generation` | string | all | |
| `body_style` | string | all | |
| `transmission` | string | all | |
| `price_type` | string | all | `auction_final`, `dealer_ask`, etc. |
| `min_sale_date` | date | 90 days ago | ISO date string |
| `max_sale_date` | date | today | |
| `min_confidence` | float | 0.0 | |
| `limit` | int | 100 | Max results (max: 500) |
| `offset` | int | 0 | |

**Response: 200 OK**

```json
{
  "total": 87,
  "comps": [
    {
      "id": "...",
      "source": "bat",
      "source_url": "...",
      "sale_date": "2025-02-28",
      "sale_price": 111000,
      "price_type": "auction_final",
      "year": 1998,
      "generation": "G6",
      "body_style": "coupe",
      "trim": "Carrera",
      "transmission": "manual",
      "exterior_color_canonical": "blue-metallic",
      "mileage": 28500,
      "matching_numbers": true,
      "original_paint": true,
      "service_history": true,
      "bidder_count": 78,
      "confidence_score": 0.96,
      "notes": null
    }
  ]
}
```

---

### GET `/clusters`

Returns all pre-computed comp clusters.

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `generation` | string | all | |
| `body_style` | string | all | |
| `insufficient_data` | bool | — | If false, only return clusters with sufficient data |

**Response: 200 OK**

```json
{
  "clusters": [
    {
      "cluster_key": "G6:coupe:manual",
      "generation": "G6",
      "body_style": "coupe",
      "transmission": "manual",
      "window_days": 90,
      "comp_count": 5,
      "median_price": 98500,
      "p25_price": 87000,
      "p75_price": 104000,
      "min_price": 79500,
      "max_price": 111000,
      "avg_confidence": 0.938,
      "insufficient_data": false,
      "last_computed_at": "2025-03-15T02:00:00Z"
    }
  ]
}
```

---

### GET `/alerts`

Returns current open (or all) alerts.

**Query params:**

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | string | `open` | `open`, `read`, `dismissed`, or `all` |
| `severity` | string | all | `info`, `watch`, `act` |
| `alert_type` | string | all | |
| `limit` | int | 50 | |

**Response: 200 OK**

```json
{
  "total": 3,
  "alerts": [
    {
      "id": "...",
      "alert_type": "underpriced",
      "triggered_at": "2025-03-15T08:15:00Z",
      "listing_id": "...",
      "reason": "1991 964 Carrera 2 at $61,000 is -18.1% below G5:coupe:manual cluster median ($74,500)",
      "delta_pct": -18.1,
      "severity": "act",
      "status": "open",
      "notified_at": null,
      "listing": {
        "source_url": "https://carsandbids.com/auctions/...",
        "year": 1991,
        "trim": "Carrera 2",
        "asking_price": 61000
      }
    }
  ]
}
```

---

### PATCH `/alerts/{id}`

Update alert status (mark as read or dismissed).

**Request body:**

```json
{
  "status": "dismissed"
}
```

**Response: 200 OK** — updated alert object.

---

### GET `/pipeline/status`

Returns recent pipeline run health.

**Response: 200 OK**

```json
{
  "runs": [
    {
      "source": "bat",
      "run_at": "2025-03-15T12:00:00Z",
      "pages_fetched": 24,
      "records_extracted": 22,
      "records_inserted": 4,
      "records_updated": 18,
      "extraction_errors": 2,
      "normalization_errors": 0,
      "duration_s": 47.3
    }
  ]
}
```

---

### POST `/listings/manual`

Manually add a listing (for sources that can't be scraped, like Facebook Marketplace).

**Request body:**

```json
{
  "source_url": "https://www.facebook.com/marketplace/item/...",
  "year": 1988,
  "generation": "G4",
  "body_style": "coupe",
  "trim": "Carrera",
  "transmission": "manual",
  "exterior_color_raw": "Granite Green Metallic",
  "mileage": 78000,
  "asking_price": 49500,
  "currency": "USD",
  "description_raw": "...",
  "listing_date": "2025-03-14",
  "seller_type": "private",
  "location": "Austin, TX"
}
```

**Response: 201 Created** — newly created listing with normalization applied.

---

## Error Responses

All errors follow:

```json
{
  "error": "not_found",
  "message": "Listing with id=X not found",
  "status_code": 404
}
```

| Status | Meaning |
|---|---|
| 400 | Invalid query params or request body |
| 404 | Resource not found |
| 422 | Validation error (Pydantic) |
| 500 | Internal server error |

---

## Authentication

MVP: no auth. API is local-only. Add API key middleware before any network exposure.
