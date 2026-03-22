# Garage Radar — Data Pipeline Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         COLLECTION LAYER                         │
│  BaT crawler  │  C&B crawler  │  PCarMarket  │  eBay API        │
└──────┬──────────────┬──────────────┬──────────────┬─────────────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        RAW SNAPSHOT STORE                        │
│              HTML / JSON blobs keyed by (source, url, ts)        │
│              Local filesystem or S3-compatible bucket            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       EXTRACTION LAYER                           │
│   Per-source parsers → structured Python dicts                   │
│   Validates required fields; logs extraction failures            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     NORMALIZATION LAYER                          │
│   • Year / generation mapping                                    │
│   • Color canonicalization (free text → standard palette)        │
│   • Transmission normalization (G50, 915, Tiptronic, etc.)      │
│   • Engine variant mapping (2.7T, 3.2 Carrera, etc.)           │
│   • NLP flags: matching numbers, orig. paint, service history    │
│   • Deduplication (VIN match → fallback heuristic cluster)      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                         POSTGRES DATABASE                        │
│   listings │ comps │ canonical_models │ alerts │ sources_log     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                       INSIGHT LAYER                              │
│   • Comp cluster builder (group similar specs)                   │
│   • Median / P25 / P75 band per spec cluster                    │
│   • Ask-vs-comp delta per listing                               │
│   • Days-on-market tracker                                       │
│   • Alert generator (threshold rules)                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                         DELIVERY LAYER                           │
│   Web dashboard (Next.js / Astro)  │  Email digest  │  Slack    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Pipeline Stages in Detail

### Stage 1: Collection

**Scheduler:** APScheduler (Python) or cron jobs — no heavy orchestration needed at MVP scale.

**Run schedule:**
- BaT / C&B: every 6 hours for active listings; daily for completed results (past 30 days)
- PCarMarket: daily
- eBay API: daily

**Crawler contract:**
- Input: source config (base URL, search params, crawl depth)
- Output: list of `RawPage(source, url, fetched_at, html_or_json)` objects
- Stores raw snapshot before parsing — always write raw first
- On HTTP error: log to `sources_log`, skip, retry next cycle

**Rate limiting:**
- Token bucket per domain: 1 token per 3s for BaT, 1/4s for C&B
- Random jitter ±20% on sleep intervals
- Respect `Retry-After` headers on 429

---

### Stage 2: Extraction

One parser module per source. Each implements:

```python
class ListingParser:
    def parse(self, raw: RawPage) -> ParsedListing | None
    def parse_result(self, raw: RawPage) -> ParsedComp | None
```

Parsed fields are typed Python dataclasses. Extraction failures log a warning and skip the record — never crash the pipeline.

**BaT-specific extraction notes:**
- Title format: `YYYY Make Model Variant [optional qualifier]`
- Spec table: structured HTML table in listing body
- Final price: prominently rendered on result pages; scrape `.auction-ended .bid-price`
- Bidder count: useful signal for demand — extract it

**C&B-specific extraction notes:**
- Title format similar to BaT
- Description text tends to be shorter — NLP extraction less reliable
- Sold price available on completed listing page

---

### Stage 3: Normalization

**Generation lookup table (air-cooled 911):**

| Years | Gen code | Common name |
|---|---|---|
| 1965–1973 | G1 | 911/912 classic |
| 1974–1977 | G2 | Impact bumper |
| 1978–1983 | G3 | SC |
| 1984–1989 | G4 | Carrera 3.2 |
| 1989–1994 | G5 | 964 |
| 1994–1998 | G6 | 993 |

**Color normalizer:** Map raw text to 20 canonical colors using fuzzy string match + known Porsche color codes (e.g., "Grand Prix White" → `white`, "Guards Red" → `red`, "Slate Grey Metallic" → `grey-metallic`). Store both raw and canonical.

**Transmission normalizer:**
- "5-speed manual", "G50", "915" → `manual`
- "Tiptronic" → `auto`
- "6-speed" → `manual` (993 Carrera RS only, note as `manual-6sp`)

**NLP flags (regex + keyword matching on description text):**
- `matching_numbers`: keywords ["matching numbers", "numbers matching", "original engine"]
- `original_paint`: ["original paint", "unrestored", "barn find", "factory color"]
- `service_history`: ["service records", "service history", "dealer maintained", "documented"]
- `modification_flags`: ["widebody", "turbo conversion", "engine rebuild", "non-original", "aftermarket"]

**Deduplication logic:**
1. Exact VIN match → deduplicate (same physical car)
2. No VIN: cluster on (year ± 0, generation, transmission, exterior_color_canonical, mileage ± 500) → flag as `possible_duplicate`, human review queue

---

### Stage 4: Database Writes

**Upsert pattern:** Insert or update on `(source, source_url)` as natural key. Never delete records — mark as `listing_status = 'removed'` if URL 404s.

**Comp finalization:** When a BaT auction closes, the listing record is updated with `final_price`, `sale_date`, and promoted to the `comps` table view.

**DB schema summary:**

```sql
-- listings: active + historical asks
listings (
  id, source, source_url, scrape_ts, listing_status,
  year, generation, body_style, transmission, engine_variant,
  exterior_color_raw, exterior_color_canonical,
  mileage, asking_price, currency,
  listing_date, seller_type, location,
  matching_numbers, original_paint, service_history, modification_flags,
  description_raw, vin,
  created_at, updated_at
)

-- comps: completed sales
comps (
  id, source, source_url,
  year, generation, body_style, transmission, engine_variant,
  exterior_color_canonical, mileage,
  sale_price, sale_date, price_type,
  matching_numbers, original_paint, service_history,
  confidence_score, notes,
  created_at
)

-- comp_clusters: pre-computed groupings for insight layer
comp_clusters (
  cluster_id, generation, body_style, transmission,
  comp_count, median_price, p25_price, p75_price,
  last_computed_at
)

-- alerts
alerts (
  id, alert_type, triggered_at, listing_id,
  reason, severity, status
)

-- pipeline_log
pipeline_log (
  id, source, run_at, pages_fetched, records_extracted,
  records_inserted, records_updated, errors, duration_s
)
```

---

### Stage 5: Insight Layer

**Comp cluster builder** (runs nightly):
- Group comps from last 90 days by (generation, body_style, transmission)
- Compute median, P25, P75 sale price for each cluster
- Require minimum 5 comps per cluster; flag clusters below threshold as `insufficient_data`
- Store results in `comp_clusters` table

**Ask-vs-comp delta** (computed at query time or on listing upsert):
- Find matching cluster for listing's (generation, body_style, transmission)
- `delta_pct = (asking_price - cluster_median) / cluster_median`
- Positive = asking above median; negative = asking below

**Alert rules (MVP):**
- `UNDERPRICED`: delta_pct < -15% AND listing age < 3 days → fire alert
- `PRICE_DROP`: asking_price decreased since last scrape by > 5% → fire alert
- `RELIST`: listing reappeared after 404 (possible relisting) → fire info alert
- `NEW_LISTING`: any new listing matching user's saved criteria → fire alert (daily digest)

---

### Stage 6: Delivery

**Dashboard:** Query Postgres directly (or via a thin FastAPI endpoint). No caching needed at MVP scale.

**Email digest:** Daily cron at 8am ET. Query open alerts + new listings. Render a simple HTML email. Send via SendGrid free tier or SMTP.

**Slack webhook:** Optional. POST alert summaries to a channel on trigger.

---

## Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Crawler | Python + httpx + BeautifulSoup | Simple, proven, easy async |
| Scheduler | APScheduler (in-process) | No infra; swap to Celery if needed |
| Storage (raw) | Local filesystem (dev) / S3 (prod) | Cheap; enables replay |
| Database | Postgres 15 | JSONB for flexibility; good full-text search |
| ORM | SQLAlchemy 2.0 | Typed; alembic migrations |
| API | FastAPI | Simple, typed, async-ready |
| Dashboard | Astro or Next.js (simple) | Static or light SSR |
| Email | SendGrid (free tier 100/day) | Dead simple |
| Hosting | Single VPS or local dev machine | No need for K8s at MVP |

---

## Failure Modes and Recovery

| Failure | Impact | Recovery |
|---|---|---|
| Source blocks scraper | Data gap for that source | Retry with backoff; alert operator |
| Parser regression | Records fail extraction | Log + skip; raw snapshot preserved for replay |
| DB disk full | Pipeline stalls | Alert on disk usage >80%; purge old snapshots |
| Comp cluster insufficient | No delta computed | Show "insufficient data" in UI; don't guess |
| Dedup miss | Duplicate comp inflates data | Flag for manual review; don't auto-delete |
