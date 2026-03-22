# Garage Radar — Phased Implementation Plan

## Guiding Principle

Ship insight before shipping infrastructure. Each phase ends with something Tucker can actually use, not just more code.

---

## Phase 0 — Foundation (Week 1)

**Goal:** Repo exists, Postgres runs locally, reference data bootstrapped.

**Tasks:**
- [ ] Create Git repo (`garage-radar`) with monorepo layout from REPO_STRUCTURE.md
- [ ] Write `docker-compose.yml` with Postgres 15
- [ ] Write SQLAlchemy models and initial Alembic migration
- [ ] Bootstrap `canonical_models` table with air-cooled 911 generation data (years, gen codes, common variants)
- [ ] Write `.env.example` and `config.py` (pydantic-settings)
- [ ] Write `Makefile` with targets: `db-up`, `migrate`, `test`, `dev`
- [ ] Confirm: `make db-up && make migrate` runs clean

**Deliverable:** Empty database with correct schema, running locally.

---

## Phase 1 — First Data (Weeks 2–3)

**Goal:** 50+ real air-cooled 911 comps in the database from BaT.

**Tasks:**
- [ ] Implement `shared/http_client.py` with rate limiting + UA rotation
- [ ] Implement `bat/crawler.py` — fetch BaT category page for Porsche 911, paginate, collect listing URLs
- [ ] Implement `bat/parser.py` — extract structured fields from a BaT listing page
- [ ] Save HTML snapshots to `data/snapshots/bat/`
- [ ] Implement `normalize/generation.py` and `normalize/transmission.py`
- [ ] Implement basic `normalize/nlp_flags.py` (regex only — matching numbers, original paint)
- [ ] Write `scripts/backfill_bat.py` — crawl past 90 days of completed BaT 911 auctions
- [ ] Run backfill; confirm 50+ records in `comps` table
- [ ] Write `tests/test_parsers.py` against saved HTML fixtures

**Deliverable:** 50+ BaT comps in Postgres. Parser tests passing. Can query the database manually.

---

## Phase 2 — Insight Engine (Week 4)

**Goal:** Comp clusters computed, ask-vs-comp delta working, can answer "is this listing cheap?"

**Tasks:**
- [ ] Implement `insights/comp_clusters.py` — group comps by (generation, body_style, transmission); compute median/P25/P75
- [ ] Implement `insights/delta.py` — match listing to cluster, compute delta_pct
- [ ] Wire `normalize/dedup.py` — flag likely duplicates in the comp set
- [ ] Add C&B crawler + parser (mirrors BaT structure)
- [ ] Run combined backfill (BaT + C&B); get to 100+ comps
- [ ] Write SQL queries for: top comps by cluster, listing delta ranking
- [ ] Manually inspect: does the cluster median feel right for a 993 Carrera Coupe?

**Deliverable:** Can run a query and see: "current 993 Carrera Coupe median comp: $X, here are 3 current listings ranked by how cheap they are."

---

## Phase 3 — Dashboard v1 (Weeks 5–6)

**Goal:** Browser-based dashboard. Stop looking at raw SQL.

**Tasks:**
- [ ] Implement FastAPI app with three endpoints:
  - `GET /listings` — active listings with delta_pct
  - `GET /comps` — recent comps, filterable by generation + transmission
  - `GET /alerts` — current open alerts
- [ ] Build Astro (or Next.js) frontend:
  - Listings table with colored delta badge (green = cheap, red = expensive)
  - Comps table with generation/transmission filters
  - Cluster summary cards (median price per gen)
- [ ] Run locally, accessible at `localhost:3000`
- [ ] Implement `normalize/color.py` — color canonicalization with alias table

**Deliverable:** Working local dashboard. Can browse listings and comps in the browser.

---

## Phase 4 — Alerting (Week 7)

**Goal:** The system tells Tucker when something interesting appears — he doesn't have to check.

**Tasks:**
- [ ] Implement `insights/alerts.py` — rule engine:
  - `UNDERPRICED`: delta < -15%, listing age < 3 days
  - `PRICE_DROP`: price decreased since last scrape > 5%
  - `NEW_LISTING`: new listing matching saved criteria
- [ ] Set up daily email digest at 8am ET (SendGrid free tier or SMTP)
- [ ] Implement scheduler (`scheduler/jobs.py`) to run:
  - Crawl + normalize every 6h
  - Cluster recompute nightly
  - Alert check + email daily
- [ ] Implement `pipeline_log` writes — track run health

**Deliverable:** Daily email arrives with flagged listings. Tucker can ignore the dashboard and just read the email.

---

## Phase 5 — Hardening & Expand Sources (Week 8+)

**Goal:** Reliable enough to use daily without babysitting.

**Tasks:**
- [ ] Add PCarMarket crawler + parser
- [ ] Add `possible_duplicate` review queue to dashboard
- [ ] Add `pipeline_log` health page to dashboard (last run, error count)
- [ ] Implement Playwright fallback for BaT if httpx gets blocked
- [ ] Add manual comp entry form (paste a URL or fill in fields manually)
- [ ] Write docs: how to add a new source

**Deliverable:** System runs unattended. Tucker only touches it when he wants to, not because it's broken.

---

## Phase 6 — Validation & Go/No-Go (Week 10–12)

**Goal:** Decide whether this is worth turning into a product.

**Questions to answer:**
- Has the alert engine surfaced anything Tucker would have missed manually?
- Are the comp clusters accurate enough to trust?
- Is there an audience for this beyond Tucker?
- What would it cost to license data instead of scraping?
- Is there a niche community (e.g., Rennlist, Pelican Parts forums) where this would spread?

**Go criteria for Phase 7 (public product):**
- [ ] At least 3 alerts flagged in 8 weeks that Tucker agrees were genuinely interesting
- [ ] Comp clusters feel accurate (manual spot-check against BaT auction history)
- [ ] At least 2 people in Tucker's network say "I would pay for this"
- [ ] A path to legal data access exists (licensing or user-contributed)

---

## Phase 7+ — Product (Post-Validation, Not Scoped Yet)

If Phase 6 is a go:
- Multi-user accounts (invite-only beta)
- Saved watchlists and criteria per user
- Second niche (water-cooled 911? Vintage Land Cruiser?)
- Mobile-friendly UI
- Community-contributed comp submissions
- Possible data licensing agreement with BaT or Hagerty

**Not scoped now.** Write it down and move on.

---

## Milestones Summary

| Phase | Week | Deliverable |
|---|---|---|
| 0 | 1 | Repo + DB running |
| 1 | 2–3 | 50+ BaT comps in Postgres |
| 2 | 4 | Ask-vs-comp delta working; 100+ comps |
| 3 | 5–6 | Local dashboard live |
| 4 | 7 | Daily email alerts working |
| 5 | 8+ | Reliable unattended operation |
| 6 | 10–12 | Go/no-go decision |
| 7 | TBD | Public product (if go) |
