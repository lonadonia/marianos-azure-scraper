# Provider comparison for Mariano's (release 1.8.0rc5, 2026-11-02)

Target: store 53100502 (Mariano's Vernon Hills) **PICKUP**. Lakeshore East (53100503, In Store) was 1.7.0's
development store; its rows are carried from that task's comparison (`D170:PROVIDER_COMPARISON.md`) and say so.
This task tested one provider live: the Oxylabs Web API. The plan and stop rules are in [`evidence/plan/TEST_PLAN_180.md`](../evidence/plan/TEST_PLAN_180.md)
(Amendments 1-2 for the probes, 3-7 for the runs, 8-9 for the census), each written before the requests it
governs. Units are never added across providers.

## 1. One table across the modes (demonstrated capabilities)

| Mode (product) | Kind of route | Store + fulfillment | Real page advancement | New unique products | Repeated success | Detail, PPM, offers | Refusals observed | Recovery | Usage | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| **D Oxylabs Web API**, `marianos` source, through the collector (this task) | scraper API returning the retailer's HTML from the provider's own browser (`run_js` on some requests); no local browser, no proxies | **yes**: every answered page of the probes, the four runs and the census states 53100502 and PICKUP in its own page state | **yes on `/pl/` listings** (`?page=N`, L9-L12; 58 pages in Q2, up to page 10); **no on `/search`** (page 2 = page 1, L18) | Q2: 1,160 products (1,137 valid fresh) from rows 22-27; Q1c: 362 (351 valid) | Q1c, Q2 and the census all served; Q1 and Q1b stopped on collector defects, not refusals | PPM, sale prices, volume offers and packs from the listing cards; product pages failed at the provider (L3, L16: HTTP 500, free), so none is used | none from the retailer. Provider failures: Q2 19 of 85 submissions brought no page (HTTP 500 free, 502, time-outs, broken connections) | segments, leases and the ledger: two hard kills, one unplanned stop and one automatic resume recovered live | 159 submissions, USD 0.2160 at the reserve rate (this task) | **primary route**: real pagination on `/pl/` inside the 250-product window |
| A ZenRows Browser (1.7.0, carried) | provider-managed browser over CDP | not reached (Lakeshore East) | not reached | 0 | 0 of 2 sessions | – | 403, 429 at the first retailer document | – | 17 credits | not qualified |
| B ZenRows Fetch (1.7.0, carried) | scraper API | **no**: the provider's default store; store instructions refused | no | 32 cards at the wrong store | 1 of 5 | default store only | 403, 429 | – | 51 credits | not qualified |
| C Scrapfly Cloud Browser (1.6.0, carried) | provider-managed browser | listing served once, before the store step | not reached | 0 | 1 of 3 | – | 403 | – | 113 credits | not qualified; not used in this task (0 credits) |
| E Oxylabs Web Unblocker (1.6.0, carried) | proxy endpoint with rendering | default store only | continuation faulted | 0 | – | – | faults on `/pl/` | – | about USD 0.018 | not qualified |
| F Playwright + Oxylabs Residential (1.6.0, carried) | local browser through residential proxies | not reached | not reached | 0 | 0 of 2 | – | edge reset; 429 | – | about USD 0.038 | not qualified |
| G Scrape.do (carried) | scraper API | not run | – | – | – | – | earlier 502 and 429 (2026-10-21) | – | 0 | not run |
| H Kroger API | official API | production 401 (1.7.0); this task: 2 location requests to the **certification** host only, a lead and never product data ([`evidence/live-probes/K1_locations_lead.json`](../evidence/live-probes/K1_locations_lead.json)) | – | – | – | test data never fills production fields | – | – | 2 free requests | blocked for production |
| I Oxylabs Classic | scraper API (Classic) | **no credentials**; the probe is frozen offline ([`classic-probe/CLASSIC_PROBE.md`](../classic-probe/CLASSIC_PROBE.md)) | – | – | – | – | – | – | 0 | unavailable; offline probe only |

No combination of services was tried. The Web API alone keeps the store and Pickup and pages `/pl/` listings, so
nothing justified moving cookie or session state across vendors, which is not to be assumed.

## 2. What the Web API does at Vernon Hills Pickup (probes L1-L20, runs, census)

| Capability | Result | Evidence |
|---|---|---|
| Store and fulfillment | honoured on every answered page | page state `locationId` 53100502, `activeModalityType` PICKUP; [`evidence/live-probes/`](../evidence/live-probes/), `evidence/live-runs/*/db/store_attestations.csv` |
| `/pl/` listing pages | served; `?page=N` returns ranks 25-48, 49-72, … | L2, L9, L10; Q1c and Q2 |
| Result window | 250 products (`availableCount`); page 11 served, page 12 failed at the provider (free) | L12, L13 |
| `/search` paging | page 2 repeats page 1 (24 of 24 products) | L18; cause (provider or retailer) not established |
| Department and child listings | served, with their trees and counts (department pages) | L11, L15, the census |
| Brand filter | narrows a `/pl/` listing (277 → 8) and a search (511 → 9) | L20, L8 |
| Price filter | not established: the search form is ignored (L7); the bucket form failed at the provider twice (L14 free, L19 time-out) | L7, L14, L19 |
| Product pages | failed at the provider (HTTP 500, free) | L3, L16 |
| `/pb/` brand route | served without product data | L5 |
| Department pages of four departments | answered with the site's search still loading (no counts): Pantry, Beverages, Frozen, Personal Care | census [`evidence/census/`](../evidence/census/) |
| Reliability | Q2: 66 of 85 submissions answered; failures took 31.2 minutes of 57.7 | [`evidence/accounting/REQUEST_LEDGER.csv`](../evidence/accounting/REQUEST_LEDGER.csv), [`COST_AND_RUNTIME_REPORT.md`](COST_AND_RUNTIME_REPORT.md) |

## 3. Recommendation

- **Primary: the Oxylabs Web API through the collector, as delivered (1.8.0rc5).** It keeps Vernon Hills Pickup
  on every page and reads `/pl/` listings page by page.
- **Its limits:**
  - Listings above the 250-product window are read through their child listings or, when a listing names none,
    through the site's brand filter (implemented and tested offline, not yet run live). A listing whose readings
    do not account for its total stays incomplete and is reported as such.
  - Brand partitions cost 4.5 to 5.7 times the pages of the categories above the window
    ([`COST_AND_RUNTIME_REPORT.md`](COST_AND_RUNTIME_REPORT.md)).
  - Provider failures dominate the runtime.
- **Fallback: none qualified.** No other mode is switched in silently. The collector records its provider per run,
  and it would have to re-verify the store context after any change.
- **Not recommended:** concealing browser automation signals, rotating identities after a refusal, or solving
  challenges. These are excluded by the project's rules.
