# Garage Radar — Normalization Pipeline Notes

> How raw listing data becomes clean, queryable records.

---

## Overview

Every listing flows through this sequence:

```
RawPage (HTML/JSON snapshot)
    │
    ▼
ParsedListing (source-specific parser)
    │
    ▼
normalize_generation()      — year → G1–G6 enum
normalize_body_style()      — free text → coupe/targa/cabriolet/speedster
normalize_transmission()    — free text → manual/auto
normalize_color()           — free text → 20-value canonical palette
extract_nlp_flags()         — description → boolean signals
compute_confidence()        — score 0–1 based on field completeness
    │
    ▼
dedup_check()               — VIN match → heuristic cluster → flag
    │
    ▼
DB upsert (listings table)
```

---

## Normalization Modules

### `normalize/generation.py`

- Input: `year: int`, optional `description: str`
- Output: `Optional[str]` — `G1`–`G6` or `None`
- Loads `normalize/generation_table.json` at runtime
- Handles ambiguous years: 1989 (G4 vs G5) and 1994 (G5 vs G6)
- Disambiguation uses keyword scan on description text
- Returns conservative earlier generation if ambiguous and no hints found

**Edge cases:**
- 1989 Speedster → G4 (even though 964 launched in 1989)
- 1994 early model year cars can be either G5 (964 built until Jan 1994) or G6 (993 from Mar 1994)
- Titles that say just "1989 Porsche 911" without further context → G4 (conservative)

---

### `normalize/color.py`

- Input: `raw_color: Optional[str]`
- Output: `(canonical: Optional[str], confidence: float)`
- Three-stage matching:
  1. Exact alias lookup (confidence 1.0)
  2. Fuzzy string match via `rapidfuzz.fuzz.token_sort_ratio` (confidence = score/100)
  3. Fallback to `"other"` (confidence 0.0)
- Alias table: `normalize/color_aliases.json` — ~180 aliases → 20 canonical values
- Always stores raw color in `exterior_color_raw` regardless of normalization result

**Common problem cases:**
- "Minerva Blue Metallic" → `blue-metallic` ✅ (in aliases)
- "Rubystone Red" → `red` ✅ (fuzzy match)
- "Special Order Viola" → likely `purple` via fuzzy, low confidence
- "Slate" (without qualifier) → ambiguous; `grey` or `grey-metallic` — pick `grey`, note low confidence
- Custom colors: return `other`, confidence 0.0

---

### `normalize/nlp_flags.py`

Regex + keyword matching on `description_raw`. No ML.

**Three-value semantics (important):**
- `True` — keyword found, flag likely applies
- `False` — negation keyword found, flag explicitly absent
- `None` — not mentioned; **unknown, not assumed false**

This matters for comps: a `matching_numbers=None` record should NOT be treated the same as `matching_numbers=False` in cluster math. Treat `None` as "condition unknown" and handle in confidence scoring.

**NLP flag accuracy estimates (based on BaT listing style):**
| Flag | Precision | Recall | Notes |
|---|---|---|---|
| `matching_numbers` | ~90% | ~85% | BaT sellers almost always mention this |
| `original_paint` | ~85% | ~75% | "Repainted" is often mentioned; silence is ambiguous |
| `service_history` | ~80% | ~70% | "No records" is explicit; presence less consistent |
| `modification_flags` | ~75% | ~60% | Easy to miss subtle mods in short descriptions |

**Improving NLP accuracy over time:**
- Add more alias variants as you see new patterns in raw descriptions
- Build a manual review queue for low-confidence records
- Consider a small fine-tuned classifier for modification detection (Phase 4+)

---

### Transmission Normalization

Simple keyword rules (implemented inline in each parser, standardized here):

| Raw text patterns | Canonical |
|---|---|
| "5-speed manual", "G50", "G50/00", "915", "5-speed" | `manual` |
| "6-speed manual", "6-speed" | `manual-6sp` |
| "Tiptronic", "automatic", "auto" | `auto` |

Notes:
- G50 = 5-speed used in 964/993 (not 6-speed)
- 993 Carrera RS uses a 6-speed; label `manual-6sp`
- If neither "manual" nor "auto" can be determined → `None`

---

### Body Style Normalization

| Raw text patterns | Canonical |
|---|---|
| "coupe", "coup", default if no mention | `coupe` |
| "targa", "Targa" | `targa` |
| "cabriolet", "cabrio", "convertible" | `cabriolet` |
| "speedster", "Speedster" | `speedster` |

---

### Confidence Score Computation

A rough 0–1 score reflecting how much we trust the normalization. Stored as `normalization_confidence`.

Starts at 1.0, deducted for each issue:

| Issue | Deduction |
|---|---|
| Year not in title / ambiguous year unresolved | -0.15 |
| Generation not determined | -0.15 |
| Transmission unknown | -0.10 |
| Body style not explicitly stated | -0.05 |
| Color normalized to "other" | -0.05 |
| Color confidence < 0.8 (fuzzy match) | -0.05 |
| Missing VIN | -0.05 |
| Possible duplicate flagged | -0.10 |
| Matching numbers = None (not mentioned) | -0.05 |

**Threshold guidance:**
- ≥ 0.85: High confidence — include in cluster math normally
- 0.65–0.84: Medium — include but weight less in cluster median
- < 0.65: Low — include in raw data but flag for review; exclude from cluster math by default

---

## Deduplication

**Goal:** Don't inflate the comp database with the same car appearing on multiple sources.

**Stage 1: VIN match**
- If two records share the same VIN, they're the same car
- The newer record is marked `possible_duplicate_id → older_record.id`
- Neither is deleted — flag for human review

**Stage 2: Heuristic cluster (no VIN)**
When VIN is absent, flag as `possible_duplicate` if all of:
- Same year (exact)
- Same generation (derived)
- Same transmission
- Same `exterior_color_canonical`
- Mileage within ±500 miles
- Listing dates within 60 days of each other

**Stage 3: Human review queue**
- Dashboard shows flagged pairs for manual confirmation
- Operator marks as "confirmed duplicate" or "different car"
- Confirmed duplicates are excluded from cluster math; raw records preserved

**Known false-positive scenarios:**
- Two different red 1987 Carrera coupes with similar mileage (happens — 987 Carreras were popular)
- Same car relisted on two sources simultaneously
- Action: show both sources on the duplicate review page; URL diff usually makes it obvious

---

## Pipeline Error Handling Philosophy

- **Never crash the pipeline on a single bad record.** Log it, skip it, continue.
- **Never delete raw snapshots.** They enable replay when parsers improve.
- **Log extraction errors per source** in `pipeline_log` — a spike in errors signals a site structure change.
- **Fail loudly on infrastructure errors** (DB unreachable, disk full) — these need operator attention.

---

## Known Normalization Hard Cases

| Scenario | Current handling | Future improvement |
|---|---|---|
| Turbo-look non-turbo cars | Body style normalizes fine; no flag for Turbo-look | Add `turbo_look` modification flag |
| Euro-spec cars with different options | `notes` field; no special handling | Add `market` field (US/EU) in v2 |
| Engine swaps (e.g., 3.6 in a 964) | `modification_flags: ['engine_swap']` | Consider separate `engine_variant_installed` vs `engine_variant_original` |
| Porsche-built 912E (1976 US only) | Year → G2; engine variant = `2.0-4cyl` | Add `912` as a body variant or separate niche? |
| RSR / race cars | `modification_flags` will catch major mods; confidence drops | Manual review queue |
| Crashed/rebuilt title cars | `title_status` field; NLP looks for "salvage" | Verify title_status is always filled |
