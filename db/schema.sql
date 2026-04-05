-- ============================================================
-- Garage Radar — Full DDL
-- Postgres 15+
-- Niche: Air-cooled Porsche 911 (1965–1998)
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- ENUMS
-- ============================================================

CREATE TYPE source_enum AS ENUM (
    'bat',
    'carsandbids',
    'pcarmarket',
    'ebay',
    'dealer_manual',
    'manual'
);

CREATE TYPE listing_status_enum AS ENUM (
    'active',
    'ended',
    'sold',
    'removed',
    'relist'
);

CREATE TYPE generation_enum AS ENUM (
    'G1',  -- 1965–1973 classic/long-hood
    'G2',  -- 1974–1977 impact bumper
    'G3',  -- 1978–1983 SC era
    'G4',  -- 1984–1989 Carrera 3.2
    'G5',  -- 1989–1994 964
    'G6'   -- 1994–1998 993
);

CREATE TYPE body_style_enum AS ENUM (
    'coupe',
    'targa',
    'cabriolet',
    'speedster'
);

CREATE TYPE transmission_enum AS ENUM (
    'manual',
    'manual-6sp',   -- 993 RS only
    'auto'          -- Tiptronic
);

CREATE TYPE drivetrain_enum AS ENUM (
    'rwd',
    'awd'   -- 964 C4 / 993 C4 only
);

CREATE TYPE title_status_enum AS ENUM (
    'clean',
    'salvage',
    'unknown'
);

CREATE TYPE currency_enum AS ENUM (
    'USD',
    'GBP',
    'EUR'
);

CREATE TYPE price_type_enum AS ENUM (
    'auction_final',
    'dealer_ask',
    'private_ask',
    'estimate'
);

CREATE TYPE alert_type_enum AS ENUM (
    'underpriced',
    'price_drop',
    'new_listing',
    'relist',
    'insufficient_data_warning'
);

CREATE TYPE alert_severity_enum AS ENUM (
    'info',
    'watch',
    'act'
);

CREATE TYPE alert_status_enum AS ENUM (
    'open',
    'read',
    'dismissed'
);

CREATE TYPE seller_type_enum AS ENUM (
    'dealer',
    'private',
    'auction_house'
);

-- Color canonical palette (20 values)
CREATE TYPE color_canonical_enum AS ENUM (
    'white',
    'silver',
    'grey',
    'grey-metallic',
    'black',
    'red',
    'blue',
    'blue-metallic',
    'green',
    'green-metallic',
    'yellow',
    'orange',
    'brown',
    'beige',
    'gold-metallic',
    'purple',
    'turquoise',
    'burgundy',
    'bronze-metallic',
    'other'
);

-- ============================================================
-- TABLE: listings
-- Active and historical asks
-- ============================================================

CREATE TABLE listings (
    -- Identity
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source                  source_enum NOT NULL,
    source_url              TEXT NOT NULL,
    scrape_ts               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    listing_status          listing_status_enum NOT NULL DEFAULT 'active',

    -- Vehicle attributes
    year                    SMALLINT NOT NULL CHECK (year BETWEEN 1965 AND 1998),
    generation              generation_enum,
    body_style              body_style_enum,
    trim                    TEXT,                       -- Carrera, Turbo, RS, etc.
    drivetrain              drivetrain_enum DEFAULT 'rwd',
    engine_variant          TEXT,                       -- '3.2', '3.6', '2.7T', etc.
    transmission            transmission_enum,
    exterior_color_raw      TEXT,
    exterior_color_canonical color_canonical_enum,
    interior_color_raw      TEXT,
    mileage                 INTEGER CHECK (mileage >= 0),
    vin                     TEXT,
    title_status            title_status_enum DEFAULT 'unknown',

    -- Price
    asking_price            NUMERIC(10,2),
    currency                currency_enum DEFAULT 'USD',
    price_history           JSONB DEFAULT '[]'::jsonb,  -- [{price: N, ts: ISO8601}, ...]
    final_price             NUMERIC(10,2),              -- Set when auction closes

    -- NLP signals (extracted from description text)
    matching_numbers        BOOLEAN,
    original_paint          BOOLEAN,
    service_history         BOOLEAN,
    modification_flags      TEXT[],                     -- e.g. ['widebody', 'engine_swap']
    normalization_confidence FLOAT CHECK (normalization_confidence BETWEEN 0 AND 1),

    -- Raw / meta
    description_raw         TEXT,
    listing_date            DATE,
    seller_type             seller_type_enum,
    seller_name             TEXT,
    location                TEXT,
    bidder_count            INTEGER,                    -- BaT/C&B auction demand proxy
    snapshot_path           TEXT,                       -- Path to raw HTML snapshot
    possible_duplicate_id   UUID REFERENCES listings(id),

    -- Timestamps
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    UNIQUE (source, source_url)
);

CREATE INDEX idx_listings_generation ON listings(generation);
CREATE INDEX idx_listings_year ON listings(year);
CREATE INDEX idx_listings_status ON listings(listing_status);
CREATE INDEX idx_listings_source ON listings(source);
CREATE INDEX idx_listings_scrape_ts ON listings(scrape_ts DESC);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_listings_updated_at
    BEFORE UPDATE ON listings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- TABLE: comps
-- Confirmed completed transactions
-- ============================================================

CREATE TABLE comps (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source                  source_enum NOT NULL,
    source_url              TEXT NOT NULL,
    listing_id              UUID REFERENCES listings(id),   -- FK if derived from a listing

    -- Transaction details
    sale_date               DATE NOT NULL,
    sale_price              NUMERIC(10,2) NOT NULL CHECK (sale_price > 0),
    currency                currency_enum DEFAULT 'USD',
    price_type              price_type_enum NOT NULL DEFAULT 'auction_final',

    -- Vehicle attributes (denormalized for query performance)
    year                    SMALLINT NOT NULL CHECK (year BETWEEN 1965 AND 1998),
    generation              generation_enum,
    body_style              body_style_enum,
    trim                    TEXT,
    engine_variant          TEXT,
    transmission            transmission_enum,
    exterior_color_canonical color_canonical_enum,
    mileage                 INTEGER CHECK (mileage >= 0),

    -- Quality signals
    matching_numbers        BOOLEAN,
    original_paint          BOOLEAN,
    service_history         BOOLEAN,
    bidder_count            INTEGER,

    -- Confidence: auction_final ~0.95, dealer_ask ~0.4, estimate ~0.2
    confidence_score        FLOAT NOT NULL DEFAULT 0.5 CHECK (confidence_score BETWEEN 0 AND 1),
    notes                   TEXT,                           -- Human annotation

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (source, source_url)
);

CREATE INDEX idx_comps_generation ON comps(generation);
CREATE INDEX idx_comps_sale_date ON comps(sale_date DESC);
CREATE INDEX idx_comps_generation_body_trans ON comps(generation, body_style, transmission);
CREATE INDEX idx_comps_price_type ON comps(price_type);

-- ============================================================
-- TABLE: canonical_models
-- Reference: valid air-cooled 911 spec universe
-- Pre-seeded; rarely changes
-- ============================================================

CREATE TABLE canonical_models (
    id                  SERIAL PRIMARY KEY,
    generation          generation_enum NOT NULL,
    years_start         SMALLINT NOT NULL,
    years_end           SMALLINT NOT NULL,
    common_name         TEXT NOT NULL,
    known_trims         TEXT[],
    known_engine_variants TEXT[],
    comp_weight         FLOAT DEFAULT 1.0,    -- Higher = RS / rare variants get more weight
    notes               TEXT
);

-- ============================================================
-- TABLE: comp_clusters
-- Pre-computed price bands. Rebuilt nightly by insight engine.
-- ============================================================

CREATE TABLE comp_clusters (
    id                  SERIAL PRIMARY KEY,
    cluster_key         TEXT NOT NULL UNIQUE,   -- '{generation}:{body_style}:{transmission}'
    generation          generation_enum NOT NULL,
    body_style          body_style_enum NOT NULL,
    transmission        transmission_enum NOT NULL,
    window_days         INTEGER NOT NULL DEFAULT 90,
    comp_count          INTEGER NOT NULL DEFAULT 0,
    median_price        NUMERIC(10,2),
    p25_price           NUMERIC(10,2),
    p75_price           NUMERIC(10,2),
    min_price           NUMERIC(10,2),
    max_price           NUMERIC(10,2),
    avg_confidence      FLOAT,
    insufficient_data   BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE if comp_count < 5
    last_computed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: alerts
-- Signals worth surfacing to the user
-- ============================================================

CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_type      alert_type_enum NOT NULL,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    listing_id      UUID REFERENCES listings(id),
    reason          TEXT NOT NULL,
    delta_pct       FLOAT,                  -- For underpriced alerts
    severity        alert_severity_enum NOT NULL DEFAULT 'info',
    status          alert_status_enum NOT NULL DEFAULT 'open',
    notified_at     TIMESTAMPTZ             -- When included in email digest
);

CREATE INDEX idx_alerts_status ON alerts(status);
CREATE INDEX idx_alerts_triggered_at ON alerts(triggered_at DESC);
CREATE INDEX idx_alerts_listing_id ON alerts(listing_id);

-- ============================================================
-- TABLE: pipeline_log
-- Crawl run health tracking
-- ============================================================

CREATE TABLE pipeline_log (
    id                      SERIAL PRIMARY KEY,
    source                  source_enum NOT NULL,
    run_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pages_fetched           INTEGER DEFAULT 0,
    records_extracted       INTEGER DEFAULT 0,
    records_inserted        INTEGER DEFAULT 0,
    records_updated         INTEGER DEFAULT 0,
    extraction_errors       INTEGER DEFAULT 0,
    normalization_errors    INTEGER DEFAULT 0,
    duration_s              FLOAT,
    notes                   TEXT
);

CREATE INDEX idx_pipeline_log_source ON pipeline_log(source, run_at DESC);

-- ============================================================
-- VIEW: active_listings_with_delta
-- Convenience view joining listings to comp cluster delta
-- ============================================================

CREATE VIEW active_listings_with_delta AS
SELECT
    l.id,
    l.source,
    l.source_url,
    l.year,
    l.generation,
    l.body_style,
    l.trim,
    l.transmission,
    l.exterior_color_canonical,
    l.mileage,
    l.asking_price,
    l.listing_date,
    l.matching_numbers,
    l.original_paint,
    l.service_history,
    l.modification_flags,
    l.normalization_confidence,
    cc.median_price AS cluster_median,
    cc.p25_price AS cluster_p25,
    cc.p75_price AS cluster_p75,
    cc.comp_count,
    cc.insufficient_data,
    CASE
        WHEN cc.median_price IS NOT NULL AND cc.median_price > 0
        THEN ROUND(((l.asking_price - cc.median_price) / cc.median_price * 100)::numeric, 1)
        ELSE NULL
    END AS ask_vs_median_pct,
    (NOW() - l.listing_date::timestamptz)::interval AS days_on_market
FROM listings l
LEFT JOIN comp_clusters cc
    ON cc.cluster_key = (l.generation::text || ':' || l.body_style::text || ':' || l.transmission::text)
WHERE l.listing_status = 'active';
