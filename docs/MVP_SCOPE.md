# Garage Radar — MVP Scope

## The Wedge

**One niche. One promise. Ship it fast.**

**Chosen niche:** Air-cooled Porsche 911 (generations: 911/912, 914, 930 Turbo, 964, 993)
- Years: 1965–1998 (everything before the water-cooled 996)
- Why: deepest auction volume on BaT/C&B, strong enthusiast signal, prices vary wildly by spec → comps genuinely matter
- Why not broader: adding water-cooled 911s triples the spec surface area and muddies comp logic
- Expansion path: 996/997 water-cooled can be Phase 2 if traction exists

---

## MVP Promise

> "Know what an air-cooled 911 is actually worth before you click 'bid'."

Three concrete outputs the MVP must deliver:
1. **Current listings** — every active auction or listing for the niche, normalized
2. **Recent comps** — completed sales in the last 90 days with key attributes
3. **Ask vs comp spread** — is this listing priced above, below, or in-line with recent comps?

---

## In Scope (MVP)

### Data collection
- Bring a Trailer (BaT) — auction listings + completed results
- Cars & Bids — auction listings + completed results
- PCarMarket — Porsche-specific auction listings + results
- Facebook Marketplace (manual import / CSV for now — too fragile to scrape reliably)

### Normalization
- Map every listing to canonical fields (year, generation, body style, transmission, color, mileage, engine variant)
- Light NLP on description text to extract: matching numbers, original paint, service history flags, modifications noted
- Deduplicate across sources by VIN or (year + color + mileage ± 500 mi) heuristic

### Storage
- Postgres (listings + comps + canonical models + alerts)
- Raw HTML/JSON snapshots archived in S3 or local store for replay

### Interface (MVP = internal dashboard only)
- Simple web UI (Next.js or plain Astro static page)
- Table: current listings with comp delta column
- Table: recent comps (90-day window, filterable by generation, body style, transmission)
- Alert list: new listings that are ≥15% below median comp for their spec cluster

### Alerting
- Email digest (daily) of new listings flagged as interesting
- Slack webhook optional

---

## Out of Scope (MVP)

- Multi-niche support (no generic "any car" search)
- Public user accounts / multi-tenant
- Mobile app
- Valuation certificates / printable reports
- Integration with financing or insurance
- Social features (comments, communities)
- Machine-learning price prediction (use statistical bands only at first)

---

## Success Criteria for MVP

The MVP is done when:
- [ ] 100+ air-cooled 911 comps are stored and browsable
- [ ] New listings from BaT appear in the dashboard within 24 hours of going live
- [ ] Ask vs comp spread is calculated and displayed for every active listing
- [ ] At least one alert fires that a human agrees is genuinely interesting
- [ ] The operator (Tucker) finds it more useful than manually browsing BaT

---

## MVP Timeline Target

| Milestone | Target |
|---|---|
| Niche confirmed, sources verified | Week 1 |
| Scraper v1 (BaT + C&B) running | Week 2–3 |
| 100 comps normalized in Postgres | Week 4 |
| Dashboard v1 live (local) | Week 5–6 |
| Alert emails working | Week 7 |
| First real insight generated | Week 8 |
