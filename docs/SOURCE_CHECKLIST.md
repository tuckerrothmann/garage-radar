# Garage Radar — Source Verification Checklist

Before writing a crawler for any source, verify each item. Update this doc when status changes.

---

## How to Use

For each source, complete the checklist before writing any crawl code. If a red item can't be resolved, document the workaround or skip the source.

Status symbols: ✅ Verified | ⚠️ Caution | ❌ Blocker | ⬜ Not checked

---

## Bring a Trailer (bringatrailer.com)

**Priority:** Tier 1 — First to implement

| # | Check | Status | Notes |
|---|---|---|---|
| 1 | `robots.txt` allows `/listing/*` pages | ⬜ | Check `bringatrailer.com/robots.txt` |
| 2 | Listing pages render server-side (no JS required) | ⬜ | Load listing URL with httpx; verify HTML contains price data |
| 3 | Completed auction results page renders price without JS | ⬜ | Critical — this is the comp data |
| 4 | Category page for Porsche 911 exists and paginates | ⬜ | `bringatrailer.com/porsche/911/` |
| 5 | Title format confirmed: `YYYY Make Model Variant` | ⬜ | Check 5 recent listings manually |
| 6 | Spec table HTML structure identified | ⬜ | Inspect element; note CSS class for spec block |
| 7 | Final price CSS selector identified | ⬜ | e.g., `.bid-price` on completed auction |
| 8 | Bidder count selector identified | ⬜ | |
| 9 | Cloudflare / bot detection present? | ⬜ | httpx test — does it return 200 or 403/503? |
| 10 | ToS reviewed | ⚠️ | Prohibits commercial scraping. Personal/research use only at MVP. See RISKS.md R1. |
| 11 | Rate limit: 1 req / 3s tested | ⬜ | Run 10 requests; verify no block |

**Known HTML targets (validate before coding):**
```
Category page:   bringatrailer.com/porsche/911/
Active listing:  bringatrailer.com/listing/{slug}
Completed:       Same URL — price shown on auction close
Pagination:      ?page=N on category page (verify)
```

**Parser field map (fill in after inspection):**
| Field | CSS selector / approach | Notes |
|---|---|---|
| Title | `h1.listing-title` | Verify |
| Final price | `.bid-price` or `.current-bid` | Verify on a closed auction |
| Spec table | `table.listing-essentials` | Verify |
| Description | `div.post-body` | Long text block |
| Listing date | `meta[property="article:published_time"]` | ISO8601 |
| Location | Spec table row "Location" | |
| Bidder count | `.bid-count` | Verify |

---

## Cars & Bids (carsandbids.com)

**Priority:** Tier 1 — Implement alongside BaT

| # | Check | Status | Notes |
|---|---|---|---|
| 1 | `robots.txt` allows search and listing pages | ⬜ | Check `carsandbids.com/robots.txt` |
| 2 | Listing pages render server-side (no JS required) | ⬜ | httpx test |
| 3 | Search URL for completed Porsche 911 auctions | ⬜ | `carsandbids.com/search/?q=porsche+911&sold=1` — verify this works |
| 4 | Sold price visible on completed auction page | ⬜ | Verify location of final price in HTML |
| 5 | Pagination of search results | ⬜ | Confirm `?page=N` or similar |
| 6 | Title format confirmed | ⬜ | Check 5 recent listings |
| 7 | CSS selectors for key fields identified | ⬜ | Price, specs, description |
| 8 | Cloudflare / bot detection present? | ⬜ | httpx test |
| 9 | ToS reviewed | ⚠️ | Restricts collection of *user* data; vehicle data less clearly restricted. Personal use only. |
| 10 | Rate limit: 1 req / 4s tested | ⬜ | |

**Known HTML targets (validate before coding):**
```
Search (active):   carsandbids.com/search/?q=porsche+911
Search (sold):     carsandbids.com/search/?q=porsche+911&sold=1
Listing:           carsandbids.com/auctions/{slug}
```

---

## PCarMarket (pcarmarket.com)

**Priority:** Tier 2 — After BaT + C&B stable

| # | Check | Status | Notes |
|---|---|---|---|
| 1 | `robots.txt` reviewed | ⬜ | |
| 2 | Listing pages render server-side | ⬜ | httpx test |
| 3 | URL structure for Porsche 911 listings identified | ⬜ | |
| 4 | Completed auction price visible | ⬜ | |
| 5 | Porsche-specific fields (PPI history, chassis certs) | ⬜ | These add comp quality if extractable |
| 6 | Pagination | ⬜ | |
| 7 | ToS reviewed | ⚠️ | Standard boilerplate — personal use stance applies |
| 8 | Rate limit: 1 req / 6s | ⬜ | |

---

## eBay Motors (via Finding API)

**Priority:** Tier 3 — Phase 2. Use **API only**, never scrape eBay.

| # | Check | Status | Notes |
|---|---|---|---|
| 1 | eBay developer account created | ⬜ | `developer.ebay.com` |
| 2 | App ID (Client ID) obtained | ⬜ | Free to register |
| 3 | Finding API `findCompletedItems` tested | ⬜ | Keywords: "porsche 911", year filter |
| 4 | Response includes sale price | ⬜ | `sellingStatus.currentPrice` |
| 5 | Category filter for Classic Cars identified | ⬜ | eBay category 6001 or similar |
| 6 | Rate limits reviewed | ⬜ | Free tier: 5,000 calls/day |
| 7 | Data quality assessed | ⚠️ | eBay listing quality is inconsistent; plan filtering heuristics |

**API reference:**
```
https://svcs.ebay.com/services/search/FindingService/v1
  ?OPERATION-NAME=findCompletedItems
  &SERVICE-VERSION=1.0.0
  &SECURITY-APPNAME={EBAY_APP_ID}
  &RESPONSE-DATA-FORMAT=JSON
  &REST-PAYLOAD
  &keywords=porsche+911+air+cooled
  &categoryId=6001
  &itemFilter(0).name=SoldItemsOnly
  &itemFilter(0).value=true
  &sortOrder=EndTimeSoonest
  &paginationInput.entriesPerPage=100
```

---

## Collecting Cars (collectingcars.com)

**Priority:** Tier 2 — Optional; useful for comp breadth, especially UK/EU pricing

| # | Check | Status | Notes |
|---|---|---|---|
| 1 | `robots.txt` reviewed | ⬜ | |
| 2 | Listing pages render server-side | ⬜ | httpx test |
| 3 | Prices in GBP — currency handling | ⬜ | Need USD conversion at comp insert time |
| 4 | Completed auction results accessible | ⬜ | |
| 5 | ToS reviewed | ⚠️ | UK-based; GDPR applies. Personal use only. |

---

## Manual Import (Facebook Marketplace / Craigslist)

**Approach:** No scheduled scraping. User-triggered via `POST /listings/manual` API endpoint.

| # | Check | Status | Notes |
|---|---|---|---|
| 1 | Manual listing form in dashboard | ⬜ | Low priority; add in Phase 5 |
| 2 | Price type always labeled `private_ask` | ✅ | Defined in schema |
| 3 | Confidence score default for manual = 0.4 | ✅ | Defined in data model |

---

## Source Status Summary

| Source | Access method | Phase | Legal status | Ready? |
|---|---|---|---|---|
| Bring a Trailer | HTML scraping | 1 | ⚠️ Personal use only | ⬜ Pre-flight pending |
| Cars & Bids | HTML scraping | 1 | ⚠️ Personal use only | ⬜ Pre-flight pending |
| PCarMarket | HTML scraping | 2 | ⚠️ Personal use only | ⬜ Not started |
| eBay Motors | Official API | 2 | ✅ API TOS OK | ⬜ Needs app ID |
| Collecting Cars | HTML scraping | 2 | ⚠️ Personal use only | ⬜ Not started |
| Facebook Marketplace | Manual import | 3 | ✅ No scraping | ⬜ Backlog |
| Craigslist | Manual import | 3 | ✅ No scraping | ⬜ Backlog |

---

## Pre-Crawl Verification Steps (run before first production crawl)

1. Fetch `robots.txt` — read it; don't just assume
2. Make 3–5 test requests to target pages; confirm 200 responses with expected content
3. Check if Cloudflare or bot detection fires — look for CAPTCHA challenge pages
4. Confirm title/price CSS selectors against 3 different listings (they vary!)
5. Snapshot 5 real HTML pages to `data/fixtures/` before writing the parser
6. Write parser against fixtures first — don't fetch live during parser dev
7. Run `make lint && make test` before first live crawl
