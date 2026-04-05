# Current State

This document is the shortest truthful summary of where Garage Radar stands now.

## Implemented

- Crawlers and parsers exist for:
  - Bring a Trailer
  - Cars & Bids
  - PCA Market
  - eBay
- Raw page snapshots are written before parsing.
- Normalization exists for:
  - generation
  - body style
  - transmission
  - color
  - simple description flags
- Postgres models and Alembic migration are in place.
- FastAPI routes exist for:
  - listings
  - comps
  - comp clusters
  - alerts
  - health and scheduler status
- APScheduler job wiring exists for crawl jobs and the insight pipeline.
- Alert notification support exists for SendGrid and Slack.
- A Next.js frontend exists for the main dashboard surfaces.

## Recently Validated

- backend editable install works
- backend test suite passes locally
- FastAPI app entrypoint works through `garage_radar.api.main:app`
- scheduler entrypoint works through `python -m garage_radar.scheduler`
- `scripts/dev.py` can bootstrap `.env`, run a local doctor check, pass through to `docker compose`, and build a local cached frontend image through `python scripts/dev.py frontend-image`
- Docker Desktop stack is running locally, with the dashboard and API reachable on `http://localhost:3000` and `http://localhost:8000`
- listing detail pages now expose richer market context including comp bands, pricing signals, recent sales scaffolding, and related-variant coverage

## Known Gaps

- The planning docs still overstate how early-stage the repo is.
- Frontend Docker rebuilds are still vulnerable to external registry/network hiccups on a cold cache, even though the new cached-image helper path is much more reliable here.
- Ruff reports a large pre-existing lint backlog; that needs a dedicated cleanup pass instead of opportunistic edits.

## Current Improvement Priorities

1. Keep the docs truthful and current.
2. Make the local workflow smoother on Windows and Unix.
3. Keep hardening ingestion and normalization around provenance, parser drift, and source consistency.
