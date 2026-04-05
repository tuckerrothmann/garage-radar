# Garage Radar

Market intelligence and comps tracking for air-cooled Porsche 911s, focused on helping a buyer understand what a car is actually worth before clicking bid.

## Current State

This repo is no longer just scaffolding. Today it includes:

- source crawlers and parsers for Bring a Trailer, Cars & Bids, PCA Market, and eBay
- a normalization pipeline for generation, body style, transmission, color, and simple NLP flags
- a Postgres schema with Alembic migrations
- a FastAPI backend for listings, comps, clusters, and alerts
- an APScheduler worker for crawl and insight jobs
- notifications for SendGrid and Slack
- a Next.js frontend for listings, comp clusters, and alerts

The planning docs in this repo are still useful, but some of them describe the original build plan rather than the current implementation. Use [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) as the authoritative status snapshot.

## What Was Recently Validated

- backend editable install works from `backend/.venv`
- backend tests pass: `205 passed`
- `garage_radar.api.main:app` is a valid app entrypoint
- `python -m garage_radar.scheduler` is a valid scheduler entrypoint

## Product Scope

Garage Radar started as an air-cooled Porsche 911 tracker, but the current
repo is now much broader:

- multi-source listing ingestion across many makes and models
- configurable vehicle targeting through `VEHICLE_TARGET_*` env vars and presets
- make/model/year-aware filtering in the API and dashboard
- richer listing drill-down pages with dossier, market signals, and coverage context

The original Porsche niche is still the most mature part of the product, but the
current codebase is no longer restricted to it.

## Architecture

```text
Sources (BaT, C&B, PCA Market, eBay)
    -> raw snapshots
    -> per-source parsers
    -> normalization
    -> Postgres (listings, comps, clusters, alerts)
    -> insight engine
    -> FastAPI + Next.js + notifications
```

## Quick Start

Prerequisites:

- Python 3.11+
- Docker, if you want the local Postgres container
- Node 18+, if you want to run the frontend

### Cross-platform workflow

The easiest developer entrypoint is the Python helper:

```bash
python scripts/dev.py env
python scripts/dev.py doctor
python scripts/dev.py install
python scripts/dev.py compose up -d db
python scripts/dev.py migrate
python scripts/dev.py seed
python scripts/dev.py api
```

Other useful commands:

```bash
python scripts/dev.py test
python scripts/dev.py lint
python scripts/dev.py scheduler
python scripts/dev.py compose up --build frontend api scheduler
python scripts/dev.py ingest --source bat --limit 5 --dry-run
python scripts/dev.py frontend
python scripts/dev.py frontend-image
```

### Makefile workflow

The Makefile is still available, but the backend targets now route through `scripts/dev.py`:

```bash
make install
make migrate
make seed
make api
```

### Database setup

If Docker is available:

```bash
python scripts/dev.py compose up -d db
```

If `.env` does not exist yet, create it with:

```bash
python scripts/dev.py env
```

For a full containerized stack, use:

```bash
python scripts/dev.py compose up --build
```

The frontend container uses `FRONTEND_DOCKER_API_URL` for its build-time API target.
Leave it at `http://api:8000` for Docker, and use `NEXT_PUBLIC_API_URL=http://localhost:8000`
for local `npm` development.

If Docker Hub or BuildKit is flaky, `python scripts/dev.py frontend-image` now
builds the Next.js app locally first and repackages it into the cached local
frontend runtime image, which makes frontend refreshes much more reliable on this
workspace than a cold `docker compose build frontend`.

## Data Honesty

- ask price is not the same thing as a confirmed transaction price
- thin comp clusters stay flagged as thin instead of pretending to be precise
- normalization is heuristic and intentionally exposes confidence fields
- raw snapshots are stored so parsing and normalization decisions can be replayed later

## Key Docs

- [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md): current implementation status and known gaps
- [`docs/DATA_PIPELINE.md`](docs/DATA_PIPELINE.md): ingestion and normalization flow
- [`docs/API_SCHEMA.md`](docs/API_SCHEMA.md): API surface
- [`docs/SOURCE_STRATEGY.md`](docs/SOURCE_STRATEGY.md): source approach and caveats
- [`docs/RISKS.md`](docs/RISKS.md): operational and product risks
- [`docs/PHASES.md`](docs/PHASES.md): original phased plan

## Known Gaps

- docs outside the README are partly a mix of current design and historical planning
- Docker frontend rebuilds can still be sensitive to external registry/network issues on a cold cache
- the lint baseline is still noisy and needs a dedicated cleanup pass
