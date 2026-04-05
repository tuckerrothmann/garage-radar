# Garage Radar — Data Model

*Niche: Air-cooled Porsche 911 (1965–1998, generations G1–G6)*

---

## Design Principles

1. **Store raw, derive clean.** Raw HTML is archived; structured fields are normalized. Normalization errors don't corrupt the raw record.
2. **Price type is sacred.** Always distinguish `auction_final` from `dealer_ask` from `private_ask`. Never average them without weighting.
3. **Uncertainty is explicit.** Confidence scores and `insufficient_data` flags are first-class. Don't hide bad data behind confident-looking numbers.
4. **Never delete, only retire.** Listings are marked `removed`; comps are permanent. Historical record is the moat.

---

## Entities

### 1. `listings` — Active and historical asks

Represents a vehicle currently for sale or historically listed (not yet confirmed sold).

**Source & identity:**
| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Internal PK |
| `source` | enum | `bat`, `carsandbids`, `pcarmarket`, `ebay`, `dealer_manual` |
| `source_url` | text | Natural key (unique per source) |
| `scrape_ts` | timestamptz | When last fetched |
| `listing_status` | enum | `active`, `ended`, `sold`, `removed`, `relist` |

**Vehicle attributes:**
| Field | Type | Notes |
|---|---|---|
| `year` | smallint | 1965–1998 |
| `generation` | enum | `G1`–`G6` (see generation table) |
| `body_style` | enum | `coupe`, `targa`, `cabriolet`, `speedster` |
| `trim` | text | Carrera, Turbo, RS, Carrera RS, SC, etc. |
| `drivetrain` | enum | `rwd`, `awd` (964/993 C4 only) |
| `engine_variant` | text | `2.0`, `2.2`, `2.4`, `2.7`, `2.7T`, `3.0`, `3.2`, `3.6`, `3.8` |
| `transmission` | enum | `manual`, `manual-6sp`, `auto` |
| `exterior_color_raw` | text | As-listed (e.g., "Grand Prix White") |
| `exterior_color_canonical` | enum | Normalized palette (20 values) |
| `interior_color_raw` | text | Free text |
| `mileage` | int | Miles (null if unknown) |
| `vin` | text | If available |
| `title_status` | enum | `clean`, `salvage`, `unknown` |

**Price:**
| Field | Type | Notes |
|---|---|---|
| `asking_price` | numeric(10,2) | Current ask in USD |
| `currency` | char(3) | `USD`, `GBP`, `EUR` |
| `price_history` | jsonb | Array of {price, ts} for price drop detection |
| `final_price` | numeric(10,2) | Set when auction closes (populated from comp) |

**Signals (NLP flags from description):**
| Field | Type | Notes |
|---|---|---|
| `matching_numbers` | boolean | Engine/gearbox match chassis |
| `original_paint` | boolean | Factory original paint claimed |
| `service_history` | boolean | Records mentioned |
| `modification_flags` | text[] | List of detected mods (e.g., `["widebody", "engine_swap"]`) |
| `normalization_confidence` | float | 0–1; low = review recommended |

**Raw & meta:**
| Field | Type | Notes |
|---|---|---|
| `description_raw` | text | Full listing description |
| `listing_date` | date | When listed |
| `seller_type` | enum | `dealer`, `private`, `auction_house` |
| `seller_name` | text | |
| `location` | text | City, State or Country |
| `bidder_count` | int | BaT/C&B only — proxy for demand |
| `snapshot_path` | text | Path to raw HTML snapshot |
| `possible_duplicate_id` | UUID | FK to suspected duplicate listing |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | |

---

### 2. `comps` — Completed transactions

Represents a confirmed sale. Auction finals are the highest-quality comps.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `source` | enum | Same enum as listings |
| `source_url` | text | Original listing URL |
| `listing_id` | UUID | FK to listings (if derived from a listing) |
| `sale_date` | date | Auction close or transaction date |
| `sale_price` | numeric(10,2) | Final price in USD |
| `currency` | char(3) | |
| `price_type` | enum | `auction_final`, `dealer_ask`, `private_ask`, `estimate` |
| `year` | smallint | |
| `generation` | enum | |
| `body_style` | enum | |
| `trim` | text | |
| `engine_variant` | text | |
| `transmission` | enum | |
| `exterior_color_canonical` | enum | |
| `mileage` | int | |
| `matching_numbers` | boolean | |
| `original_paint` | boolean | |
| `service_history` | boolean | |
| `bidder_count` | int | Auction demand proxy |
| `confidence_score` | float | 0–1; `auction_final` = 0.95+; `dealer_ask` = 0.4 |
| `notes` | text | Human annotation |
| `created_at` | timestamptz | |

---

### 3. `canonical_models` — Reference: air-cooled 911 spec universe

Pre-seeded lookup table. Defines the valid combinations the system recognizes.

| Field | Type | Notes |
|---|---|---|
| `id` | serial | |
| `generation` | enum | G1–G6 |
| `years_start` | smallint | |
| `years_end` | smallint | |
| `common_name` | text | "964", "993 Carrera", etc. |
| `known_trims` | text[] | Carrera, RS, Turbo, Carrera 4, etc. |
| `known_engine_variants` | text[] | |
| `comp_weight` | float | Relative weight when building clusters (e.g., RS comps matter more) |
| `notes` | text | |

---

### 4. `comp_clusters` — Pre-computed price bands

Rebuilt nightly by the insight layer.

| Field | Type | Notes |
|---|---|---|
| `id` | serial | |
| `cluster_key` | text | `{generation}:{body_style}:{transmission}` |
| `generation` | enum | |
| `body_style` | enum | |
| `transmission` | enum | |
| `window_days` | int | 90 or 180 (widened for thin clusters) |
| `comp_count` | int | Number of comps in window |
| `median_price` | numeric | |
| `p25_price` | numeric | |
| `p75_price` | numeric | |
| `min_price` | numeric | |
| `max_price` | numeric | |
| `avg_confidence` | float | Average confidence_score of included comps |
| `insufficient_data` | boolean | True if comp_count < 5 |
| `last_computed_at` | timestamptz | |

---

### 5. `alerts` — Signals worth surfacing

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `alert_type` | enum | `underpriced`, `price_drop`, `new_listing`, `relist`, `insufficient_data_warning` |
| `triggered_at` | timestamptz | |
| `listing_id` | UUID | FK to listings |
| `reason` | text | Human-readable explanation |
| `delta_pct` | float | For `underpriced` alerts |
| `severity` | enum | `info`, `watch`, `act` |
| `status` | enum | `open`, `read`, `dismissed` |
| `notified_at` | timestamptz | When included in email digest |

---

### 6. `pipeline_log` — Crawl run health

| Field | Type | Notes |
|---|---|---|
| `id` | serial | |
| `source` | enum | |
| `run_at` | timestamptz | |
| `pages_fetched` | int | |
| `records_extracted` | int | |
| `records_inserted` | int | |
| `records_updated` | int | |
| `extraction_errors` | int | |
| `normalization_errors` | int | |
| `duration_s` | float | |
| `notes` | text | Error summaries |

---

## Key Derived Fields (computed, not stored)

| Field | Computation | Used for |
|---|---|---|
| `ask_vs_median_delta_pct` | `(asking_price - cluster.median) / cluster.median` | Listing ranking |
| `ask_vs_p25_delta_pct` | `(asking_price - cluster.p25) / cluster.p25` | Identifying steals |
| `days_on_market` | `NOW() - listing_date` | Staleness signal |
| `price_drop_pct` | Diff between last two entries in `price_history` | Alert trigger |
| `relist_flag` | Listing reappeared after 404 + >7 day gap | Seller motivation signal |

---

## Generation Reference

| Gen code | Years | Common name | Key variants |
|---|---|---|---|
| G1 | 1965–1973 | Classic / Long hood | 911, 912, 911S, 911T, 911E, 2.7RS |
| G2 | 1974–1977 | Impact bumper | Carrera, 930 Turbo |
| G3 | 1978–1983 | SC era | 911 SC, 930 Turbo |
| G4 | 1984–1989 | Carrera 3.2 | Carrera, Carrera Cabrio, Carrera Targa, Speedster |
| G5 | 1989–1994 | 964 | Carrera 2, Carrera 4, Turbo, RS America, Turbo 3.6 |
| G6 | 1994–1998 | 993 | Carrera, Carrera 4, Turbo, Carrera RS, Targa, Cabriolet |

---

## Color Canonical Palette (20 values)

`white`, `silver`, `grey`, `grey-metallic`, `black`, `red`, `blue`, `blue-metallic`, `green`, `green-metallic`, `yellow`, `orange`, `brown`, `beige`, `gold-metallic`, `purple`, `turquoise`, `burgundy`, `bronze-metallic`, `other`
