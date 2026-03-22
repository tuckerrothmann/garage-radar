# Garage Radar — Risks & Constraints

## Risk Register

### R1 — Source access / ToS legal risk
**Severity:** High  
**Likelihood:** Medium  
**Description:** BaT, C&B, and PCarMarket all prohibit scraping for commercial use in their ToS. Personal/research use is tolerated in practice, but there is no safe harbor guarantee. They can block access or send cease-and-desist letters.

**Mitigations:**
- Keep MVP personal use only; do not monetize while scraping
- Rate-limit aggressively (no faster than a human browsing)
- Archive raw snapshots locally — do not redistribute
- Use eBay's official API instead of scraping eBay
- At commercialization: negotiate data licensing or pivot to a model that doesn't rely on scraping (e.g., user-submitted comps, licensed data from Hagerty)
- Research whether BaT/C&B have commercial data programs before scaling

**Residual risk:** If the product gains traction, sources may notice and block. Plan for this — design the pipeline so sources can be swapped or added.

---

### R2 — Anti-scraping blocks (technical)
**Severity:** Medium  
**Likelihood:** High (eventually)  
**Description:** BaT and C&B use Cloudflare and/or bot detection. Scrapers will get blocked if they look automated.

**Mitigations:**
- Rotate User-Agent strings (pool of real browser UAs)
- Randomize sleep intervals (jitter ± 20%)
- Use residential proxy if needed (Oxylabs, Smartproxy) — but only for personal research
- Use Playwright (headless browser) as fallback if httpx gets blocked — much harder to detect
- Monitor `pipeline_log` for error rate spikes; alert operator when a source fails

**Contingency:** If BaT blocks completely, fall back to manual entry of BaT results (tedious but possible for important sales). Consider community-contributed comps as a longer-term solution.

---

### R3 — Data normalization accuracy
**Severity:** High  
**Likelihood:** High  
**Description:** Listing titles and descriptions are free text. Color, spec, and modification information is inconsistently described. Bad normalization creates bad comps, which creates bad signals.

**Mitigations:**
- Build a "normalization confidence" field — low-confidence records get flagged
- Manual review queue for ambiguous records
- Maintain a human-curated alias table (e.g., "Minerva Blue" → `blue-metallic`)
- Start narrow: only compute deltas for comp clusters with ≥5 records and high average confidence
- Log normalization failures explicitly; fix parsers before adding sources

**Key known hard cases:**
- Engine swaps (non-original displacement)
- "Euro-spec" models with different options
- Turbo-look body conversions on non-turbo cars
- Color-matched bumpers on impact-bumper cars

---

### R4 — Ask price ≠ transaction price
**Severity:** High (product design risk)  
**Likelihood:** Certain  
**Description:** Most listing sites show asking prices, not sale prices. A comp database built on asks will overstate the market. Auctions (BaT, C&B) give real transaction prices, but private/dealer sales rarely do.

**Mitigations:**
- Clearly distinguish `ask` vs `sale` price in all UI and data
- Weight auction comps more heavily in price band computation
- Never call an ask-based price a "comp" — label it "asking price"
- Add `price_type` field to every comp record: `auction_final`, `dealer_ask`, `private_ask`, `estimate`
- Consider discounting dealer asks by a haircut factor (e.g., 10%) in band computation — but make this visible to user

---

### R5 — Insufficient comp density for meaningful clusters
**Severity:** Medium  
**Likelihood:** Medium  
**Description:** Some spec clusters (e.g., 1973 911 RS replica, Turbo Cabriolet 964) may have very few comps in the 90-day window. Small samples produce unreliable price bands.

**Mitigations:**
- Require minimum 5 comps per cluster before computing a band
- Widen cluster window to 180 days for thin clusters
- Show "insufficient data" honestly in UI rather than a bad estimate
- Merge adjacent clusters if needed (e.g., 964 C2 Coupe + 964 C4 Coupe for thin niches)
- Over time, accumulate proprietary comp history — this is the moat

---

### R6 — Condition and originality can't be fully standardized
**Severity:** Medium  
**Likelihood:** Certain  
**Description:** Two 1987 Carrera Coupes may be at different price points because of originality, paint condition, or service history — factors that don't normalize to a field easily.

**Mitigations:**
- NLP flags (matching numbers, original paint, service history) are binary signals — imperfect but useful
- Do not claim a precise valuation — present a range (P25–P75)
- Show the user the raw comp records so they can judge
- Add a "notable factors" free-text field on comps for human annotation
- Over time, train a simple model on NLP flags + sale price to weight condition signals

---

### R7 — Founder motivation / sustaining effort
**Severity:** Medium  
**Likelihood:** Low (hobby project risk)  
**Description:** This is a passion project. If the niche loses interest, or the scraping becomes tedious, the project stalls.

**Mitigations:**
- Keep the first niche personally interesting (Tucker should genuinely care about air-cooled 911s)
- Make the system useful to Tucker before making it useful to anyone else
- Keep the MVP small — 8 weeks to first real insight, not 8 months
- Don't overbuild the pipeline before validating the insight quality

---

### R8 — Hagerty / competing products
**Severity:** Low (now)  
**Likelihood:** Medium (over time)  
**Description:** Hagerty, AutoTrader Classics, and ClassicCars.com all have some version of market data. Hagerty has a published valuation index.

**Mitigation:**
- Garage Radar's wedge is *freshness* (live listings + recent auction results) vs. Hagerty's quarterly index
- Garage Radar is opinionated: it surfaces *specific listings* worth looking at, not just a number
- Community-contributed niche data (eventually) creates a moat Hagerty can't easily replicate
- Differentiate on depth within the niche, not breadth

---

## Hard Constraints

| Constraint | Impact |
|---|---|
| No scraping at commercial scale without licensing | Must stay personal until data agreements exist |
| Minimum 5 comps per cluster for price band | Some rare variants won't have usable comps |
| Ask price ≠ comp — must label clearly | UI must never mislead on price type |
| Free text normalization is imperfect | Expect 10–20% normalization error rate at launch; improve over time |
| MVP = one niche only | Do not add other car niches until air-cooled 911 comps are solid |

---

## Risk Summary Matrix

| Risk | Severity | Likelihood | Priority |
|---|---|---|---|
| R1 ToS / legal | High | Medium | 🔴 Top |
| R3 Normalization accuracy | High | High | 🔴 Top |
| R4 Ask ≠ transaction | High | Certain | 🔴 Top |
| R2 Technical blocks | Medium | High | 🟡 Monitor |
| R5 Thin comp clusters | Medium | Medium | 🟡 Monitor |
| R6 Condition unquantifiable | Medium | Certain | 🟡 Mitigate in UI |
| R7 Founder motivation | Medium | Low | 🟢 Watch |
| R8 Competition | Low | Medium | 🟢 Low now |
