# Garage Radar — Source Strategy

## Niche Context

Air-cooled Porsche 911s (1965–1998) have strong transaction visibility because:
- BaT and Cars & Bids list hundreds per year with full descriptions + final prices
- PCarMarket is a Porsche-specialist auction channel
- Enthusiast dealers post inventory publicly with VINs and detailed descriptions
- The niche is small enough that every sale matters

---

## Source Tier Ranking

### Tier 1 — High priority, scrape first

#### Bring a Trailer (bringatrailer.com)
- **Why:** Largest volume of collector 911 auctions in the US; completed results are public with final prices, bidder count, and full descriptions
- **Access pattern:** Public HTML pages; no login required for completed results
- **Robots.txt:** Allows general crawling; `/listing/*` and `/porsche/911/` category pages accessible
- **Rate limit approach:** 1 req/3s, randomized UA rotation, respect Retry-After
- **ToS risk:** High — ToS prohibits scraping for commercial use. **Approach: personal/research use during MVP; re-evaluate at monetization**
- **Data quality:** Excellent — structured titles (year make model variant), inline specs table, final price prominent
- **Target pages:**
  - `bringatrailer.com/porsche/911/` — category listing (active + past)
  - Individual listing pages for detail extraction
- **Frequency:** Scrape new listings every 6 hours; completed results daily

#### Cars & Bids (carsandbids.com)
- **Why:** Strong volume; tends toward newer 964/993; lower prices than BaT = more buying opportunity signal
- **Access pattern:** Public HTML; search results paginate predictably
- **Robots.txt:** Disallows `/sell-car/`, `/widgets/`, `/dealers/` — listing and search pages OK
- **Rate limit approach:** 1 req/4s, session cookie rotation
- **ToS risk:** Medium — ToS restricts collection of *user* data; vehicle/auction data is less clearly restricted
- **Data quality:** Good — consistent listing template; final price shown on completed auctions
- **Target pages:**
  - `carsandbids.com/search/?q=porsche+911&sold=1` — completed auctions
  - Individual auction pages for full detail
- **Frequency:** Every 6 hours for active; daily sweep for past 30 days

### Tier 2 — Add after Tier 1 is stable

#### PCarMarket (pcarmarket.com)
- **Why:** Porsche-only; attracts serious specialists; descriptions tend to be more detailed about history
- **Access pattern:** Public HTML; well-structured listing pages
- **ToS risk:** Similar to BaT — no explicit scraping prohibition found but ToS standard boilerplate
- **Data quality:** Very good for Porsche-specific fields
- **Frequency:** Daily sweep

#### Collecting Cars (collectingcars.com)
- **Why:** Growing UK+US presence; useful for comp breadth; exchange rate needs handling
- **Access pattern:** Public HTML
- **Frequency:** Daily

### Tier 3 — Manual / semi-manual import only

#### eBay Motors
- **Why:** Has volume but listing quality is inconsistent; lots of non-serious sellers
- **Access:** eBay has a Finding API (free tier) — **use the official API, not scraping**
- **eBay Finding API:** `findCompletedItems` with keywords "porsche 911" + year range filter gives sold items with final prices
- **Data quality:** Mixed — require VIN or detailed spec text to normalize
- **Action:** Wire up eBay API in Phase 2

#### Facebook Marketplace / Craigslist
- **Why:** Where private sellers list; real transaction signals
- **Access:** FB actively blocks scrapers; CL is very hostile to scraping
- **Approach:** Manual CSV import UI — let user paste a URL and trigger a one-shot fetch; no scheduled crawl
- **Priority:** Low — Phase 3

#### Specialty dealers (Callas Rennsport, Brumos, etc.)
- **Why:** Known-quality cars; often priced at premium; useful as ceiling data points
- **Approach:** Hand-maintain a list of ~10 dealer inventory pages; light scraper
- **Frequency:** Weekly

---

## Source Access Architecture

```
sources/
├── bat/
│   ├── crawler.py          # BaT listing + result pages
│   └── parser.py           # HTML → structured dict
├── carsandbids/
│   ├── crawler.py
│   └── parser.py
├── pcarmarket/
│   ├── crawler.py
│   └── parser.py
├── ebay/
│   └── api_client.py       # eBay Finding API
└── shared/
    ├── rate_limiter.py     # Token bucket per domain
    ├── ua_rotation.py      # User-agent pool
    ├── http_client.py      # Requests + retry logic
    └── snapshot_store.py   # Raw HTML archive
```

---

## Data Freshness Targets

| Source | Active listings | Completed results |
|---|---|---|
| BaT | Every 6h | Daily |
| Cars & Bids | Every 6h | Daily |
| PCarMarket | Daily | Daily |
| eBay API | Daily | Daily |
| Dealers | Weekly | N/A |

---

## Legal / Ethical Position

**MVP stance:** Personal research use only. No resale of scraped data. Rate-limited and polite. Archive raw HTML locally — do not distribute.

**At monetization:** Either negotiate data agreements with BaT/C&B (they do have commercial data programs) or shift to a model where users contribute their own listing data (like a community comps database). Do not scrape at scale for a commercial product without explicit permission or a data licensing agreement.

**eBay:** Use the official API. Period.

---

## Field Extraction Priority

For each listing, the minimum viable extracted fields are:

| Field | Source availability | Notes |
|---|---|---|
| Year | Title (always) | Regex on title |
| Make/Model | Title | Always present |
| Generation | Derived from year | Lookup table |
| Trim/variant | Title + description | Carrera, Targa, Turbo, RS, etc. |
| Transmission | Title or description | 5-speed, G50, Tiptronic |
| Mileage | Spec table | Usually explicit |
| Exterior color | Title or description | Free text, needs normalizer |
| Asking/final price | Price field | Final price = comp; asking = listing |
| Sale date / listing date | Page metadata | Auction close date |
| Source URL | Always | Primary key |
| Engine variant | Description | 2.0, 2.2, 2.4, 2.7, 3.0, 3.2, etc. |
| Matching numbers | Description text | NLP flag |
| Original paint | Description text | NLP flag |
| Service history noted | Description text | NLP flag |
| Modifications noted | Description text | NLP flag |
