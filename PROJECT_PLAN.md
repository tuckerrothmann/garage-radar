# Garage Radar - Project Plan

## Working thesis
The collector / vintage vehicle market is information-rich but structurally messy. Buyers who can organize listing data, comp data, and vehicle-specific signals into a usable view gain a meaningful edge.

## Personal benefit
This could be useful even before it is a business:
- learn a niche vehicle market deeply
- track listings without manual searching
- compare asking prices against actual recent transactions
- identify interesting opportunities and outliers

## Initial user
An enthusiast who cares deeply about a specific collector niche and wants better visibility into:
- current inventory
- recent transactions
- pricing trends
- vehicle quality / originality signals

## Core promise
Track the real market for a niche collector vehicle and quickly see what looks overpriced, fair, or interesting.

## Non-goal
This is not a generic used-car marketplace.
It should not start as a broad valuation engine for every car.

## MVP

### Scope
One narrow niche only.
Examples:
- air-cooled Porsche 911s
- vintage Toyota Land Cruisers
- classic Ford Broncos
- BMW E30 M3s
- classic Mercedes SL models

### Inputs
- selected listing sites
- auction result sites
- dealer inventory pages
- manual or semi-manual comp inputs where needed

### Core fields
- year
- make
- model
- trim / variant
- mileage
- transmission
- color
- condition notes
- modifications
- location
- asking price
- transaction price if available
- source URL
- listing date / sale date

### Outputs
- current listings dashboard
- recent comps table
- ask vs comp spread
- fair-value band estimate
- watchlist / alerts for relevant new listings
- possible outlier flags

## Ideal v1 workflow
1. User chooses a niche and saved criteria
2. System collects new listings and comp data
3. System normalizes key attributes
4. System compares current asks to known comps
5. System surfaces listings worth a closer look

## Why this could work
- clear enthusiast utility
- narrow, data-driven wedge
- naturally accumulates proprietary structured data over time
- personally interesting enough to sustain work on it

## Biggest risks
- scraping and source terms / access limitations
- duplicate listings across sites
- inconsistent condition descriptions
- difficult valuation due to originality and modifications
- not all niches have enough transparent transaction data

## Product wedge
Position it as:
"market radar for a collector niche"
not
"AI that tells you what every car is worth"

## Validation plan

### Phase 1: niche and source selection
- choose one vehicle niche
- identify 2-4 sources with enough volume and usable data
- verify access patterns and scrape practicality

### Phase 2: data normalization prototype
- collect a sample of 50-100 records
- normalize key fields
- manually inspect data quality issues
- build a first comps table

### Phase 3: insight prototype
- define what counts as a useful signal
- produce weekly updates or alerts
- compare flagged opportunities against manual judgment

## Questions to answer next
- What is the first niche?
- Which sources are worth the effort?
- Which fields matter most for valuation?
- Can condition / originality be standardized well enough for useful comping?
- Should the first version be mostly dashboard, alerting, or research notebook?

## Success metric for early use
The tool reliably saves time and surfaces listings or market insights that would have been missed by casual browsing.
