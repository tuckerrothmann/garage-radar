# Garage Radar — Repo & App Structure

## Monorepo Layout

```
garage-radar/
├── README.md
├── .env.example
├── docker-compose.yml          # Postgres + app for local dev
├── Makefile                    # Common tasks: migrate, scrape, dev, test
│
├── backend/                    # Python pipeline + API
│   ├── pyproject.toml
│   ├── alembic/                # DB migrations
│   │   ├── env.py
│   │   └── versions/
│   ├── garage_radar/
│   │   ├── __init__.py
│   │   ├── config.py           # Settings (env vars via pydantic-settings)
│   │   ├── db/
│   │   │   ├── models.py       # SQLAlchemy ORM models
│   │   │   ├── session.py      # DB session factory
│   │   │   └── queries.py      # Common query helpers
│   │   ├── sources/
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # Abstract crawler + parser interfaces
│   │   │   ├── shared/
│   │   │   │   ├── http_client.py
│   │   │   │   ├── rate_limiter.py
│   │   │   │   ├── ua_rotation.py
│   │   │   │   └── snapshot_store.py
│   │   │   ├── bat/
│   │   │   │   ├── crawler.py
│   │   │   │   └── parser.py
│   │   │   ├── carsandbids/
│   │   │   │   ├── crawler.py
│   │   │   │   └── parser.py
│   │   │   ├── pcarmarket/
│   │   │   │   ├── crawler.py
│   │   │   │   └── parser.py
│   │   │   └── ebay/
│   │   │       └── api_client.py
│   │   ├── normalize/
│   │   │   ├── __init__.py
│   │   │   ├── generation.py   # Year → generation lookup
│   │   │   ├── color.py        # Color canonicalization
│   │   │   ├── transmission.py
│   │   │   ├── nlp_flags.py    # Regex-based text signals
│   │   │   └── dedup.py        # Deduplication logic
│   │   ├── insights/
│   │   │   ├── __init__.py
│   │   │   ├── comp_clusters.py  # Cluster builder + stats
│   │   │   ├── delta.py          # Ask-vs-comp delta
│   │   │   └── alerts.py         # Alert rule engine
│   │   ├── scheduler/
│   │   │   ├── __init__.py
│   │   │   └── jobs.py         # APScheduler job definitions
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── main.py         # FastAPI app
│   │       └── routers/
│   │           ├── listings.py
│   │           ├── comps.py
│   │           └── alerts.py
│   └── tests/
│       ├── test_parsers.py
│       ├── test_normalize.py
│       ├── test_insights.py
│       └── fixtures/           # Saved HTML snapshots for parser tests
│
├── frontend/                   # Dashboard UI
│   ├── package.json
│   ├── astro.config.mjs        # (or next.config.js)
│   ├── src/
│   │   ├── pages/
│   │   │   ├── index.astro     # Active listings dashboard
│   │   │   ├── comps.astro     # Recent comps table
│   │   │   └── alerts.astro    # Alert list
│   │   ├── components/
│   │   │   ├── ListingTable.tsx
│   │   │   ├── CompTable.tsx
│   │   │   ├── DeltaBadge.tsx  # Color-coded ask-vs-comp badge
│   │   │   └── AlertCard.tsx
│   │   └── lib/
│   │       └── api.ts          # API client (fetch wrapper)
│   └── public/
│
├── scripts/
│   ├── bootstrap_db.py         # Create tables + seed generation lookup
│   ├── backfill_bat.py         # One-shot historical backfill for BaT
│   └── export_comps.csv.py     # Dump comps to CSV for analysis
│
└── docs/                       # Project documentation
    ├── MVP_SCOPE.md
    ├── SOURCE_STRATEGY.md
    ├── DATA_PIPELINE.md
    ├── REPO_STRUCTURE.md       ← this file
    ├── RISKS.md
    └── PHASES.md
```

---

## Key Design Decisions

### Monorepo, not microservices
MVP scale doesn't justify separate services. Backend (Python) and frontend (JS) share a repo. FastAPI serves the API; Astro/Next.js serves the UI. One `docker-compose.yml` runs everything locally.

### Thin API, thick pipeline
The pipeline (crawl → normalize → insert → compute insights) is the core product. The API is just a thin read layer over Postgres. Don't over-engineer the API early.

### Raw snapshot archive first
Always store raw HTML before parsing. This enables:
- Parser regression testing with real data
- Historical backfill when parsers improve
- Debugging without re-fetching

### Parser tests with fixtures
Save a sample of real HTML snapshots in `tests/fixtures/`. Parser tests run against fixtures, not live sites. This makes the test suite fast and offline-safe.

---

## Local Dev Setup

```bash
# 1. Clone and enter
git clone git@github.com:yourname/garage-radar.git
cd garage-radar

# 2. Start Postgres
docker-compose up -d db

# 3. Backend setup
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 4. Run migrations
alembic upgrade head

# 5. Bootstrap reference data (generations, etc.)
python scripts/bootstrap_db.py

# 6. Run scraper once
python -m garage_radar.sources.bat.crawler --limit 20

# 7. Start API
uvicorn garage_radar.api.main:app --reload

# 8. Frontend setup (separate terminal)
cd ../frontend
npm install
npm run dev
```

---

## Environment Variables

```env
# .env.example
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/garage_radar
SNAPSHOT_STORE_PATH=./data/snapshots
EBAY_APP_ID=your_ebay_app_id
SENDGRID_API_KEY=your_sendgrid_key
ALERT_EMAIL_TO=you@example.com
LOG_LEVEL=INFO
```

---

## CI / Testing

Minimal CI at MVP:
- `pytest backend/tests/` — parser + normalization tests
- `ruff check backend/` — linting
- No deployment pipeline yet — run locally or SSH to VPS

When the product matures:
- Add GitHub Actions for lint + test on push
- Deploy via Docker Compose on a VPS ($5/mo Hetzner or DigitalOcean)
