# Garage Radar 🏎️

> Market intelligence and comps tracker for air-cooled Porsche 911s (1965–1998).

Know what one of these cars is actually worth before you click "bid."

---

## The Promise

Auction platforms give you a list. Garage Radar gives you context:

- **Active listings** from Bring a Trailer, Cars & Bids, and PCarMarket — normalized to the same schema
- **Completed sale comps** for the last 90 days with real transaction prices
- **Ask vs comp spread** on every active listing — is this car priced cheap, fair, or rich?
- **Alerts** when something looks underpriced or just dropped in price

---

## Status

| Phase | Status |
|---|---|
| Scoping & documentation | ✅ Complete |
| Repo scaffolding (this sprint) | ✅ Complete |
| DB schema & seed data | ✅ Ready to run |
| BaT crawler v1 | ⬜ Not started |
| C&B crawler v1 | ⬜ Not started |
| Normalization pipeline | ⬜ Not started |
| Insight engine (clusters + delta) | ⬜ Not started |
| Dashboard v1 | ⬜ Not started |
| Alerting / email digest | ⬜ Not started |

**Next action:** Phase 0 — `make db-up && make migrate`, verify schema, seed canonical_models.

---

## Quick Start (Local Dev)

**Prerequisites:** Docker, Python 3.11+, Node 18+

```bash
# 1. Clone
git clone git@github.com:yourname/garage-radar.git
cd garage-radar

# 2. Configure env
cp .env.example .env
# Edit DATABASE_URL if needed; defaults work with docker-compose

# 3. Start Postgres
make db-up

# 4. Install backend deps + run migrations
make install
make migrate

# 5. Seed reference data (generations, canonical model lookup)
make seed

# 6. Start the API
make api

# 7. (Optional) Frontend
make frontend
```

Then open `http://localhost:8000/docs` for the FastAPI swagger UI.

---

## Niche

**Air-cooled Porsche 911, 1965–1998 only.**

| Gen | Years | Common name | Key variants |
|---|---|---|---|
| G1 | 1965–1973 | Classic / Long-hood | 911, 912, 911S, 911T, 911E, 2.7RS |
| G2 | 1974–1977 | Impact bumper | Carrera, 930 Turbo |
| G3 | 1978–1983 | SC era | 911 SC, 930 Turbo |
| G4 | 1984–1989 | Carrera 3.2 | Carrera, Targa, Cabriolet, Speedster |
| G5 | 1989–1994 | 964 | Carrera 2, Carrera 4, Turbo, RS America |
| G6 | 1994–1998 | 993 (last air-cooled) | Carrera, Carrera 4, Turbo, Carrera RS |

Water-cooled 911s (996+) are out of scope for v1.

---

## Architecture Overview

```
Sources (BaT, C&B, PCarMarket)
         │
         ▼
  Raw HTML snapshots        ← always archived before parsing
         │
         ▼
  Per-source parsers        ← structured Python dicts
         │
         ▼
  Normalization layer       ← generation, color, transmission, NLP flags
         │
         ▼
  Postgres (listings, comps, clusters, alerts)
         │
         ▼
  Insight engine            ← comp clusters, ask-vs-comp delta, alert rules
         │
         ▼
  FastAPI + Astro dashboard + daily email digest
```

---

## Repo Layout

```
garage-radar/
├── README.md
├── .env.example
├── docker-compose.yml
├── Makefile
│
├── backend/
│   ├── pyproject.toml
│   ├── alembic/                  # DB migrations
│   └── garage_radar/
│       ├── config.py
│       ├── db/                   # SQLAlchemy models + session
│       ├── sources/              # Crawlers + parsers per source
│       │   ├── shared/           # Rate limiter, UA rotation, HTTP client
│       │   ├── bat/
│       │   ├── carsandbids/
│       │   ├── pcarmarket/
│       │   └── ebay/
│       ├── normalize/            # Generation, color, transmission, NLP, dedup
│       ├── insights/             # Comp clusters, delta, alert rules
│       ├── scheduler/            # APScheduler jobs
│       └── api/                  # FastAPI app + routers
│
├── frontend/                     # Astro dashboard
│
├── db/
│   ├── schema.sql                # Full DDL (reference + migration source)
│   └── seed/
│       └── canonical_models.sql  # Air-cooled 911 generation seed data
│
├── data/
│   ├── fixtures/                 # Sample normalized listing + comp JSON
│   └── snapshots/                # Raw HTML archive (gitignored)
│
├── normalize/
│   ├── color_aliases.json        # Color normalization table
│   └── generation_table.json     # Year → generation lookup
│
├── scripts/
│   ├── bootstrap_db.py
│   ├── backfill_bat.py
│   └── export_comps_csv.py
│
└── docs/
    ├── MVP_SCOPE.md
    ├── SOURCE_STRATEGY.md
    ├── DATA_PIPELINE.md
    ├── SOURCE_CHECKLIST.md       # Source verification checklist
    ├── API_SCHEMA.md             # FastAPI endpoint reference
    ├── RISKS.md
    └── PHASES.md
```

---

## Tech Stack

| Layer | Choice |
|---|---|
| Pipeline | Python 3.11 + httpx + BeautifulSoup4 |
| Scheduler | APScheduler 3.x |
| Database | Postgres 15 |
| ORM | SQLAlchemy 2.0 + Alembic |
| API | FastAPI |
| Dashboard | Astro (static) or Next.js |
| Email | SendGrid free tier |
| Dev env | Docker Compose |

---

## Data Honesty

A few things this tool is clear-eyed about:

- **Ask ≠ sale price.** Auction finals (`auction_final`) are high-quality comps. Dealer asks (`dealer_ask`) are discounted in cluster math. The distinction is always visible.
- **Thin clusters get flagged.** Less than 5 comps in 90 days? The UI says "insufficient data" — no made-up bands.
- **Normalization isn't perfect.** Expect ~10–20% of early records to have low confidence scores. They're flagged, not hidden.
- **Scraping is legally gray.** This is personal research tooling. See [SOURCE_STRATEGY.md](docs/SOURCE_STRATEGY.md) and [RISKS.md](docs/RISKS.md) for the full picture.

---

## Project Docs

| Doc | What it covers |
|---|---|
| [MVP_SCOPE.md](docs/MVP_SCOPE.md) | Exact scope, success criteria, 8-week timeline |
| [SOURCE_STRATEGY.md](docs/SOURCE_STRATEGY.md) | Which sources, access patterns, ToS position |
| [SOURCE_CHECKLIST.md](docs/SOURCE_CHECKLIST.md) | Pre-crawl verification checklist per source |
| [DATA_PIPELINE.md](docs/DATA_PIPELINE.md) | Full pipeline: collect → normalize → insight → deliver |
| [API_SCHEMA.md](docs/API_SCHEMA.md) | FastAPI endpoint reference |
| [RISKS.md](docs/RISKS.md) | Risk register with mitigations |
| [PHASES.md](docs/PHASES.md) | 8-week phased build plan with task checklists |

---

## Personal Use First

Built by Tucker, for Tucker. If the data quality holds and the insights prove genuinely useful, it may become a product. For now: a research engine that earns its keep by surfacing opportunities a manual BaT browse would miss.
