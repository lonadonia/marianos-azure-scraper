# Mariano's collector: pagination, client corrections and live qualification, release 1.8.0rc5 (2026-11-02)

> **Current state: [`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md)** (release 1.9.0rc4, 2026-11-09). This report is the 1.8.0rc5 report as published on 2026-11-02, unchanged below this note; the 1.9.0 report's §13 lists the statements of this report that it corrects.

Governing brief: "Mariano's: complete client corrections, verify the collector, and build the next reviewable
delivery" (task 1.8.0). Target store: **Mariano's Vernon Hills, store 53100502, 1720 N Milwaukee Ave, Vernon Hills,
IL 60061, PICKUP**. Lakeshore East (53100503, In Store), the 1.7.0 development store, appears here only as
historical or development evidence. Every live request of this task was sent from Hamza's workstation (Windows 11)
through Hamza's Oxylabs Web API account. Nothing ran on the client's Azure VM (section 12). All times are UTC
(Africa/Casablanca is UTC+0 on this date).

## 1. Answer in brief

| Question | Answer |
|---|---|
| Release | **1.8.0rc5**, commit `ee5ec99b27bf68f63f6026a5b2e97937abccc5d3` (development branch `marianos-1.8`; its history is not published). Its frozen tree is `source/` of this repository, file for file the `source/` of `MARIANOS_SOURCE_1.8.0rc5.zip` (SHA-256 `1832ef6e5051f20e55842057b60d37a61924e1af92d360fea6ae810104481485`, `manifests/PUBLICATION.json`). The live runs of this task ran 1.8.0rc1 to 1.8.0rc4, and every segment records its own commit. **1.8.0rc5 has not run live**: its only change after rc4 is how the integrity gate G13 treats a page the provider never delivered (section 14). It is verified offline: its full suite passed from a clean extraction of its source archive (576 tests), and the delivered package was checked from a fresh extraction ([`evidence/verification/PACKAGE_VERIFICATION.txt`](../evidence/verification/PACKAGE_VERIFICATION.txt)) |
| Pagination (client finding C01) | **Corrected.** Each `/pl/` listing is now read page by page (`?page=N`), and every page is judged before its products count. Live run Q2 completed 58 listing pages (up to page 10 of a listing) at Vernon Hills Pickup, and every page's products went through the same extraction and checks as page 1 ([`data/Q2-1.8.0rc4/LISTING_PAGES.csv`](../data/Q2-1.8.0rc4/LISTING_PAGES.csv)) |
| Fresh, retained, conflicted | Run Q2 `01M6E5V6CASQ8F00VC8PE9TFYW` (1.8.0rc4), store 53100502 PICKUP only: **1,160 products exported, 1,137 fresh valid**, 10 price conflicts (one cent each), 10 eligible but without a displayed price, 3 exported but not valid (price stated for no store). Retained 1,160 (fresh valid 1,137 + fresh not valid 23 + carried 0). 0 duplicate UPCs, 0 duplicate URLs |
| Coverage | CSV rows 23-27 **complete**; row 22 Pet Supplies **incomplete** (Cat Food: 231 distinct products of the 232 the site reports, after all 10 pages); rows 0-21 **not run** at Vernon Hills. 17 listings: 14 DONE, 2 EMPTY (the site reports 0 results), 1 INCOMPLETE. Q2 was rejected by its gates (G3 coverage, G13 integrity) and never published |
| Last-good publication | Run Q1c's publication (1.8.0rc3, rows 23-26, 351 valid) stayed the last-good dataset through Q2's rejection (pointer version 1, unchanged) |
| Client findings | 9 (C01-C09). Corrected: C01 pagination, C05 price-conflict attribution (cause still unknown, stated as such), C06 reservation left reserved, C07 store, C09 wording. Corrected as rules, live re-observation pending: C02, C03 (Buy 1 Save offers) and C04 (serving size). Partial: C08 coverage. [`CORRECTION_MAP.csv`](CORRECTION_MAP.csv) |
| Defects found during this task | 8 (T01-T08): 5 corrected (T01-T03, T08; T04 was a test defect), 3 open and minor (T05 a probe traceback, T06 an export's segment end time, T07 an event name) |
| Live / offline / synthetic / client VM | Live: probes L1-L20, runs Q1, Q1b, Q1c, Q2, the department census (stage D). Offline: replays of stored pages, census of 1.7.0rc2's records under the 1.8.0 rules, G13 re-check. Synthetic: the test suites. **Client VM: not executed** (section 12) |
| Requests and cost | Oxylabs Web API in this task: 159 submissions, USD 0.2160 at the reserve rate (probes 20 / 0.0225, runs Q1-Q2 116 / 0.1590, department census 23 / 0.0345). Cumulative for all Oxylabs products over the three tasks: USD 0.7899 (0.5739 before this task), USD 0.2101 left of the USD 1.00 allowance. Scrapfly 0. Kroger 2 requests to the certification host (free). Nothing bought. Costs are estimates at the collector's reserve rate (USD 0.0015 per submission); no invoice was read |
| Processes and schedules | No collector process, schedule or timer is left running (section 17). The collector's Oxylabs ceiling in the qualification database is 0 |

Not claimed: a complete catalogue, production readiness, the client's acceptance, or execution on the client VM.

## 2. Baseline and requirement map (brief §1)

- **Start point:** 1.7.0rc2, commit `4815ed4` on branch `marianos-1.7` (verified 2026-10-30, delivery
  `20261030_marianos_1.7.0rc2`, unchanged).
- **Requirement map:** [`ACCEPTANCE_MATRIX.csv`](ACCEPTANCE_MATRIX.csv) restates the 70 earlier client requirements (M01-M70, with their
  1.8.0 status) and the 45 requirements of this brief (B01-B45). Each row has its status, evidence class, artifact,
  remaining action, the next owner of that action (a column added in this publication) and acceptance condition. A check of a delivered file or of documentation is labelled
  `VERIFIED (package)` or `VERIFIED (documentation)`, never `LIVE VERIFIED`.
- **The client's findings, reproduced before any change:** [`evidence/offline-reprocessing/repro/finding_0081675102373.json`](../evidence/offline-reprocessing/repro/finding_0081675102373.json),
  `finding_0086001079386.json` and `finding_0073679800140.json`. They are read from 1.7.0rc2's own stored pages, and
  the tool is [`evidence/tools/repro_findings.py`](../evidence/tools/repro_findings.py).
  - Cutwater Espresso Martini, "Buy 1 Save $1", and The Finnish Long Drink, "Buy 1 Save $2": the volume pattern read
    "Buy N" as a multi-unit condition.
  - Avocado Green Goddess Dip & Spread: the size slot held the serving "2 tbsp", while the product data says
    8 OUNCES and the title "8 oz.".

## 3. Pagination (brief §3, client finding C01)

**Before.** `pagination_check()` in `collection/oxylabs_live.py` requested page 2 only to compare its identities with
page 1. It never collected page 2's products and never went further. 1.7.0rc2 therefore exported page 1 of each
listing.

**Now** (1.8.0rc1 onward):

- **The loop.** `collection/oxylabs_live.py` `read_listing` and `collection/pagination.py` fetch page 1, then
  `?page=2, 3, …` of the same `/pl/` listing, until the end the site reports. Each response is checked for:
  - the store and fulfillment in its own page state;
  - the listing and the page number it answers for;
  - its result count, the products in its page state and the product cards.
- **The verdict comes first.** Every response is judged before its products count:
  - `NEW` and `PARTIAL_OVERLAP` (genuine consecutive pages) count;
  - `REPEATED` and `REORDERED_REPEAT` (page 1 again, in the same or another order) stop the listing as incomplete;
  - `EMPTY`, `MALFORMED`, `WRONG_CONTEXT` (another store or fulfillment), `WRONG_PAGE`, `WRONG_LISTING`, `BLOCKED`
    and `FAILED` never count.
- **The checkpoint.** Migration 0004 adds `listing_pages`: one row per response with the requested and returned
  page, attempt, verdict, reported total, identities (new, duplicate, excluded, conflicting), the page's SHA-256 and
  the provider request id.
  - A listing's checkpoint advances only past a page that was validated and stored. A failed or unvalidated page
    stays unfinished.
  - A resume continues from the first unfinished page. It does not fetch completed pages again, and committed
    products are not duplicated.
- **The result window.** The site reports `totalCount` and `availableCount` (250 here; 24 products a page, page 11
  is the last one inside the window). A listing whose total is above its window is read through its child listings,
  and is complete only if the children account for its total. A listing above the window that names no child
  listing is read through the site's own brand filter: `brand_partitions()` in `collection/pagination.py`, called
  by `read_listing` in `collection/oxylabs_live.py` (setting `coverage.partition_large_listings`, on by default),
  one filtered reading per brand the page names. It is complete only if the brand readings account for its total.
  Otherwise it stays incomplete.
  - **Implemented** since 1.8.0rc1 and **tested offline** on a synthetic site
    (`test_a_leaf_above_the_window_is_read_through_the_sites_own_brand_filter` in
    [`source/tests/integration/test_listing_pages.py`](../source/tests/integration/test_listing_pages.py)).
  - **Not proven live.** No listing of Q1c or Q2 was above the window (the largest, Cat Food, reported 232), so
    neither path ran live, and complete coverage through brand readings is not shown for any category.
- **Publication protection** for incomplete coverage is unchanged: a run with an incomplete listing is never
  published.

**Regressions** (brief §3: fail on the defective code, pass on the correction):

- [`source/tests/integration/test_page_regressions.py`](../source/tests/integration/test_page_regressions.py) holds the five cases of the brief:
  - a three-page listing exports products from all three pages;
  - a page-2 failure stays unfinished and resumes correctly;
  - repeated pages stop without false completeness;
  - a wrong-store or wrong-fulfillment page cannot enter the dataset;
  - a restart neither duplicates products nor fetches completed pages again.
- Result: **6 failed on 1.7.0rc2** ([`evidence/tests/regress/old_4815ed4.log`](../evidence/tests/regress/old_4815ed4.log), the same test file importing the old tree) and
  **6 passed on 1.8.0** ([`evidence/tests/regress/new_worktree.log`](../evidence/tests/regress/new_worktree.log)).
- [`source/tests/integration/test_listing_pages.py`](../source/tests/integration/test_listing_pages.py) runs a synthetic `/pl/` site with a real worker kill
  (`os._exit`) between persistence steps.

**Live (Q2, 1.8.0rc4).** 61 listing responses ([`data/Q2-1.8.0rc4/LISTING_PAGES.csv`](../data/Q2-1.8.0rc4/LISTING_PAGES.csv)):

- 57 `NEW` and 1 `PARTIAL_OVERLAP` were completed. The partial overlap is Cat Food page 8, which repeated 1 product
  of an earlier page.
- 2 `FAILED`: Hardware page 2, provider HTTP 500 on both task attempts (not charged).
- 1 `MALFORMED`: Hardware page 3, a response with no page number or result count, refused and read again after an
  automatic resume.
- The 2 empty listings (Fish Supplies, Small Animal Supplies) answered with 0 results.
- Every page was store 53100502 PICKUP.

**Mutation check** ([`evidence/tests/regress/mutants.json`](../evidence/tests/regress/mutants.json)). 8 of 11 planned mutants of the loop were run, and each made at least
one test fail. The 9th timed out when the workstation entered standby at 06:10Z, and the runner stopped. **The
remaining 3 mutants were not run** in this delivery.

## 4. Provider diagnosis (brief §4)

Route used: **the Oxylabs Web API**, `marianos` source. This is a scraper API returning the retailer's HTML: the
provider's own browser renders the page, and `run_js` was used for some requests. The store and fulfillment are
requested as `store_id` 53100502 and `fulfillment_type` pickup, and attested on every page by the page's own state
(`locationId`, `activeModalityType`). Neither a local browser nor proxies were used. Probes L1-L20 (05:00-05:30Z,
one submission per hypothesis, no retry) are in [`evidence/live-probes/`](../evidence/live-probes/):

| Probe | Request (53100502 PICKUP) | Result | Reading |
|---|---|---|---|
| L1 | `/search` `cereal` | 200; 511 results, 250 reachable, 24 products | store and Pickup honoured. A first attempt returned 404 because Git Bash rewrote the endpoint path: my tool error, not a provider result |
| L2 | `/pl/cereal-granola/03001` | 200; 397 results, 250 reachable | the `/pl/` listing is served at this store (it was refused at Lakeshore East In Store on 10-28) |
| L3, L16 | product endpoint; a `/p/` product page | HTTP 500, "failed after too many retries" (not charged) | product pages unavailable through this route on this date |
| L4 | `/q/cereal` | HTTP 500 (not charged) | undetermined |
| L5 | `/pb/general-mills/cereal-granola/03001` | 200, no product state | the brand route gives no listing data |
| L6 | `/search?page=2` without a query | 200; the retailer's own request failed (400) with `page.offset` 24 | the page number reaches the retailer's data service as an offset |
| L7 | search with `price_range` 2.00-5.00 | 200; total 511 (unchanged) | the price-range form does not narrow the results |
| L8 | search with `brand` General Mills | 200; total 9 | the brand filter narrows a search |
| L9, L10 | `/pl/…/03001?page=2` (L10 with `run_js`) | 200; page 2, new products | **`?page=N` is honoured on `/pl/`** (ranks 25-48) |
| L11 | child listing `/pl/cold-cereal/0300100001` | 200; 277 results, 250 reachable | a child listing is served; this one is itself above the window |
| L12 | `?page=11` | 200; page 11 | the last page inside the 250 window answers |
| L13 | `?page=12` | HTTP 500 (not charged) | past the window: no page; whether this is the provider or the site is not established |
| L14, L19 | price bucket on a child listing, by name, then by the page state's own slug | HTTP 500 (not charged); provider timeout (unknown cost) | **no price partition is established** |
| L15 | department listing `/pl/breakfast/03` | 200; 949 results, 250 reachable, the department's categories with counts | a department page states its tree and counts (used by the census, section 5) |
| L18 | `/search?query=cereal&page=2` | 200; page 2 holds the same 24 products as page 1 | **`/search` repeats page 1**; the `/pl/` route does not |
| L20 | `/pl/cold-cereal/0300100001?brandName=General%20Mills` | 200; total 8 | **the brand filter narrows a `/pl/` listing**: the subdivision available for listings above the window |

Separating the causes, as the brief asks:

- **Missing collection loop:** a collector defect (C01), corrected.
- **Request construction:** the L1 404 was my tool's path rewriting, not the collector's. The collector's requests
  were correct.
- **Parsing:** two collector defects found live and corrected.
  - T02: a new product-card variant (`MiniProductCard`) served from about 12:30Z was read as 0 cards. Q1b stopped
    itself on it.
  - T01: a price stated for no store was counted valid by the record builder. Q1's canary caught it.
- **Store and session context:** honoured on every page of every run. No default-store page entered a dataset.
- **Provider pagination and windows:** `/search` page 2 repeats page 1 (L18). Whether the provider or the retailer
  causes this is a hypothesis, not established. The `/pl/` route pages correctly up to the 250 window.
- **Retailer refusal and blocking:** none in this task.
- **Authentication or entitlement:** none observed.
- **Provider failures:** HTTP 500 "failed after too many retries" (not charged), HTTP 502 and time-outs (cost
  unknown, kept as possibly charged). Q2 had 19 such submissions out of 85 (section 10).

Other providers were not used in this task. Their 1.6.0 and 1.7.0 evidence is carried in [`PROVIDER_COMPARISON.md`](PROVIDER_COMPARISON.md).
Kroger's certification host answered 2 location requests ([`evidence/live-probes/K1_locations_lead.json`](../evidence/live-probes/K1_locations_lead.json)): a lead only, never used
for production fields. Oxylabs Classic has no credentials (section 11).

## 5. Coverage (brief §5, client finding C08)

**What Q2 covered** ([`data/Q2-1.8.0rc4/COVERAGE_BY_LISTING.csv`](../data/Q2-1.8.0rc4/COVERAGE_BY_LISTING.csv), [`data/Q2-1.8.0rc4/COVERAGE_BY_CSV_ROW.csv`](../data/Q2-1.8.0rc4/COVERAGE_BY_CSV_ROW.csv), [`data/Q2-1.8.0rc4/COVERAGE_RECONCILIATION.json`](../data/Q2-1.8.0rc4/COVERAGE_RECONCILIATION.json)):

| CSV row | Listings | Pages completed | Distinct products | Status |
|---|---|---|---|---|
| 22 Pet Supplies (`/d/pet-supplies`, 12 menu listings) | 9 DONE, 2 EMPTY, 1 INCOMPLETE | 38 | 754 | **INCOMPLETE**: Cat Food 231 of 232, "accessible pages exhausted; coverage incomplete" |
| 23 Candles Home Fragrances (32001) | 1 DONE | 3 | 52 of 52 | COMPLETE |
| 24 Batteries (26003) | 1 DONE | 5 | 97 of 97 | COMPLETE |
| 25 Light Bulbs (26002) | 1 DONE | 4 | 94 of 94 | COMPLETE |
| 26 School Office (35) | 1 DONE | 5 | 119 of 119 | COMPLETE |
| 27 Hardware Home Improvement (33) | 1 DONE | 3 | 64 of 64 | COMPLETE |
| 0-21 | not run at Vernon Hills | 0 | 0 | NOT ATTEMPTED |

- **Counts.** The listings hold 1,180 listing-level identities, which are 1,160 distinct products. 20 products are
  in two listings:
  - 16 in both Batteries and Hardware;
  - 2 in both Cat Food and Cat Treats;
  - 2 in both School Office and Hardware.
- **The Cat Food gap.** The site reported 232 results on every page. Its 10 pages held 231 distinct products, and
  page 8 repeated one product of an earlier page. The listing stays incomplete. No threshold turns it complete.
- **Why rows 22 and 27 were added to Q2.** Rows 23-26 alone hold 362 products, below the 500 valid fresh products
  the brief asks one run to show (test plan, Amendment 6). Q2 is a qualification scope, not a coverage claim.

**Full scope at Vernon Hills: the department census (stage D, Amendments 8 and 9).**

- **How it was measured.** One request per department page (`/pl/<slug>/<2-digit id>`) at 53100502 PICKUP,
  covering the departments that rows 1-22 name. Each page states the department's product count and each
  category's count.
- **Result:** 17 departments measured, 4 not.
  - **Measured:** 16 by the census at 15:17-15:24Z and Breakfast by L15.
  - **Not measured:** Pantry, Beverages, Frozen and Personal Care. Their pages came back with the site's search still
    loading, and per the plan they were not retried.
  - **What the measured part holds:** 19,911 products in the 158 categories the CSV rows name. 20 categories are
    above the 250 window, and they hold 11,034 of those products.
  - **Control:** the census's Pet categories give 755 products and 38 pages, exactly the 38 pages Q2 read for row 22.
  - **Files:** [`evidence/census/FULL_SCOPE_CENSUS.csv`](../evidence/census/FULL_SCOPE_CENSUS.csv), [`evidence/census/FULL_SCOPE_BY_CSV_ROW.csv`](../evidence/census/FULL_SCOPE_BY_CSV_ROW.csv), [`evidence/census/FULL_SCOPE_ESTIMATE.json`](../evidence/census/FULL_SCOPE_ESTIMATE.json).
  - **The first attempt (14:34Z) was lost** to the workstation's standby, and 3 submissions are settled as possibly
    charged.
- **Use.** The census gives [`COST_AND_RUNTIME_REPORT.md`](COST_AND_RUNTIME_REPORT.md) the page counts for the full-scope estimate, and shows which
  categories exceed the 250 window.
- **Categories above the window** can be divided only through a retailer filter that was proven to work. That is the
  brand filter (L20); the price bucket is not established (L14, L19). The collector implements the brand path
  (section 3), tested offline. Whether a category's brand readings add up to its total has to be shown per
  category, live. It was **not** shown in this task.

## 6. Promotions (brief §6, client findings C02 and C03)

- **The rule** (`assembly/offers.py`): a condition on one unit ("Buy 1 Save $1") is not a volume offer, and the cans
  inside one retail pack are not the units of an offer. The offer's wording and terms are kept in the export's
  `offers.json`, flagged `OTHER_PROMO_UNCLASSIFIED`. The 22 fields are unchanged.
- **Regression:** [`source/tests/unit/test_client_findings_180.py`](../source/tests/unit/test_client_findings_180.py), with positive and negative cases.
- **The same rule over every volume offer 1.7.0rc2 exported** ([`evidence/offline-reprocessing/repro/VOLUME_DEALS_170_UNDER_180.csv`](../evidence/offline-reprocessing/repro/VOLUME_DEALS_170_UNDER_180.csv)): 645
  records with 647 offers. 3 move out of volume:
  - the client's two products;
  - Nutrl Vodka Hard Seltzer (0001820020352), "Buy 1 Save $2".
- **Live at Vernon Hills.** The client's three products are alcohol, which is not in rows 22-27, so the correction is
  not observed live at Vernon Hills.
- **Q2's fields:** 37 volume offers, 127 sale prices, 4 digital offers.
- **Digital offers between runs.** 42 products lost the digital coupon "Save $1.00 on Energizer" between Q1c and Q2.
  The coupon text is in each product's Q1c page and absent from its Q2 page, and each export matches its own stored
  page ([`data/Q2-1.8.0rc4/DIGITAL_OFFER_CHANGES_Q1C_Q2.csv`](../data/Q2-1.8.0rc4/DIGITAL_OFFER_CHANGES_Q1C_Q2.csv)). Both pages are captures returned by the provider: they do
  not show whether the retailer, the provider or something between them changed the response.

## 7. Serving size against pack size (brief §7, client finding C04)

- **Rules R1-R5** (`assembly/size_evidence.py`): a serving is never a pack size; a unit-measure denominator is not a
  pack size; doses, dimensions and limits are not pack measures. A conflict that the product's own observations do
  not settle leaves the size empty, and no sibling's size is borrowed.
- **Provenance.** Every observation is kept in the export's provenance, outside the 22 fields.
- **The client's product:** "2 tbsp" becomes "8 oz" (R3, serving replaced: the title and the product data agree).
- **The rules over 1.7.0rc2's saved observations** ([`evidence/offline-reprocessing/repro/SIZE_170_UNDER_180.csv`](../evidence/offline-reprocessing/repro/SIZE_170_UNDER_180.csv), 233 conflict rows):

  | Rule | Replaced | Emptied | Kept or unchanged |
  |---|---|---|---|
  | R3 | 1 | – | – |
  | R4 | 19 | 65 | 72 kept |
  | R5 | – | 39 | 35 unchanged |

  This applies the size function, not the whole record builder, to the saved observations. It is not a rebuild of
  1.7.0rc2's records.
- **Q2:** 3 records keep `SIZE_CONFLICT_UNRESOLVED`, with an empty size.

## 8. Price conflicts (brief §8, client finding C05)

- **1.7.0rc2's 120 one-cent conflicts** were re-read from their own stored pages
  ([`evidence/offline-reprocessing/conflicts/`](../evidence/offline-reprocessing/conflicts/), [`evidence/tools/conflict_trace.py`](../evidence/tools/conflict_trace.py)): 120 of 120 page hashes match and 120 of 120 structured values match.
  - The collector reads both values as text through `Decimal`, with no float.
  - The displayed value equals floor(structured × 100) / 100 computed in binary floating point. That pattern is
    consistent with an upstream truncation, but the pages do not establish whether the retailer, the provider or
    another component causes it.
- **The label.** 1.7.0rc2's label said both values come from the retailer, which is not established. It is now
  `ONE_CENT_TRUNCATION_PATTERN`, a pattern only. The old label stays in historical provenance.
- **Values and status.** The exported value is the displayed one, the record is `price_conflict` and never valid,
  and the 22-field contract is unchanged.
- **Q2:** 10 records, 10 fields, all one cent, all this pattern ([`data/Q2-1.8.0rc4/PRICE_CONFLICTS.csv`](../data/Q2-1.8.0rc4/PRICE_CONFLICTS.csv)).

## 9. Retention and unavailable products (brief §9)

- **Q1c against Q2** ([`data/Q2-1.8.0rc4/RETENTION_Q1C_Q2.csv`](../data/Q2-1.8.0rc4/RETENTION_Q1C_Q2.csv)): all 362 products of Q1c (rows 23-26) were observed again by Q2.
  - 320 were unchanged.
  - 42 changed: the Energizer coupon (section 6).
  - No product disappeared, so carried-forward retention of a product not seen again was **not exercised live** in
    this task. It is covered by the synthetic tests and by 1.7.0's carried evidence.
- **Unavailable products.** Q2 retains 10 eligible products without a displayed price, 5 of them
  `TEMPORARILY_OUT_OF_STOCK`. They are exported with empty prices and are never valid.

## 10. Recovery, publication safety and the twice-weekly question (brief §10, client finding C06)

**Forced stops, all live:**

- **Q1c, 12:40:33Z, planned hard kill** (`taskkill /F /T`) while Candles page 3 was in flight.
- **Q2, 13:13:01Z, planned hard kill** after its 4th page step.
- **Q2, 13:45:43Z, unplanned stop.** The workstation ran short of memory and the tool running the recording stopped
  its background tasks.
- **Q2, 14:09:03Z, provider error.** The run paused itself after 3 provider failures on one page and resumed
  automatically 1 minute later (1 of the 3 automatic resumes allowed).

**After each stop:**

- The next `resume` closed the old segment as abandoned and reclaimed the task's lease.
- It settled the in-flight submission as `interrupted_unknown` (possibly charged, counted once, never reset). No
  reservation stayed `reserved`. This is the corrected C06; before the fix, the recovery ran after the account check,
  so a dead worker's reservation at the ceiling could refuse its own recovery.
- It continued at the first page not completed. No completed page was fetched again, and no product was recorded
  twice. The page in flight at each stop was requested again after the resume (Q1c: Candles page 3; Q2: Dog Food
  page 5 and School Office page 5), and failed requests were retried within the run's limits (for example Hardware
  page 2: seven free HTTP 500 answers, then a completed page). Every submission is in [`evidence/accounting/REQUEST_LEDGER.csv`](../evidence/accounting/REQUEST_LEDGER.csv).

**Publication:**

- Q1c was published to the stage's own local folder on Hamza's workstation, nowhere else.
- Q2 was rejected (G3, G13), so Q1c's publication stayed last-good.
- The lineage check refuses to publish fixture records, another store's records and records with no observation
  in the run ([`source/tests/integration/test_last_good_survives.py`](../source/tests/integration/test_last_good_survives.py)).

**Runtime** ([`evidence/accounting/SEGMENTS.csv`](../evidence/accounting/SEGMENTS.csv), [`evidence/accounting/REQUEST_LEDGER.csv`](../evidence/accounting/REQUEST_LEDGER.csv)):

- Q2's segments ran 57.7 minutes in all, with one worker and requests in series.
- Its 85 submissions comprised:
  - 66 answered: 61 listing responses (median 10.0 s, 90th percentile 67.1 s), 4 robots.txt reads (one per segment)
    and 1 Coupons page; together 23.5 minutes of waiting;
  - 17 that brought no page (provider HTTP 500 or 502, time-outs, broken connections), each waiting 6 s to 3 minutes
    before failing: together **31.2 minutes**;
  - 2 in flight at the forced stops, settled as possibly charged.

Provider failures, not page counts, dominated the time. [`COST_AND_RUNTIME_REPORT.md`](COST_AND_RUNTIME_REPORT.md) turns these measurements and
the census into an estimate for a full run twice a week, with the assumptions stated.

## 11. The Mariano's Classic probe (brief §11)

- **Identity.** `oxylabs-classic-probe` 1.6.0, frozen in [`classic-probe/`](../classic-probe/), with its test plan, commands and
  offline results.
- **Live mode is disabled.** It refuses with exit 3 without an approved configuration and build. There are no
  credentials, and the client has not approved Classic execution.
- **Offline checks from the clean extraction** of the 1.8.0rc4 archive ([`evidence/classic-probe/from-1.8.0rc4-archive/`](../evidence/classic-probe/from-1.8.0rc4-archive/)) and again from 1.8.0rc5
  ([`evidence/classic-probe/from-1.8.0rc5-archive/`](../evidence/classic-probe/from-1.8.0rc5-archive/)): the same results from both.
  - Tests, ruff, mypy, `plan` and `validate`: passed.
  - `replay` with the shipped example rate card: refused by design (rates not confirmed, exit 2).
  - `replay` with a **synthetic** rate card over the probe's own test envelopes: 3 dispatches, each reserved first.
- **Aggregate limit.** The probe's shared campaign limits stay those of the separately versioned Walmart probe;
  that probe was not modified.
- **Open defect T05:** `replay` on a folder without `replay.json` ends in a Python traceback (exit 1) instead of a
  clean refusal. Nothing is sent either way. Not fixed in this delivery.
- **Documentation.** Oxylabs' current Classic pages were saved on 2026-11-02 ([`evidence/classic-probe/oxylabs-docs-20261102/`](../evidence/classic-probe/oxylabs-docs-20261102/)). The page
  `targets/marianos.md` answers "Page Not Found". No Classic parameter is assumed from the Web API.

## 12. The client's Azure VM (brief §2 and §12)

**Not executed.** The brief permits login and offline Python and Docker checks on the client's VM (its address and
user are not published here), with the host key verified at first connection.

- **The key.** The SSH agent prepared for it never held the key: Hamza had not loaded it. No login was attempted,
  and nothing was run or changed on the VM.
- **The host key.** The only contact was at 04:47Z: two scans of its SSH host key (`ssh-keyscan`; no login, no
  authentication). The ED25519 key it offered matches the fingerprint the client supplied (not published here).
- **The shutdown.** The VM's original automatic shutdown was 15:57Z today. Whether the extension was granted is not
  known.
- **What stays to be done** is listed in [`ACCEPTANCE_RUNBOOK.md`](ACCEPTANCE_RUNBOOK.md): the offline build, the tests and the Docker
  check. No provider credential, rate or live request is ever to be used there.

Hamza's own Azure VM (used in 1.7.0) was not used in this task, and its state was not checked here.

## 13. Live qualification (brief §13)

Plan and ceilings: [`evidence/plan/TEST_PLAN_180.md`](../evidence/plan/TEST_PLAN_180.md) (Amendments 3-7 govern the Q stage, 8-9 the census). Each amendment was
written before the requests it governs.

| Run | Release | Time | Submissions | Outcome |
|---|---|---|---|---|
| Q1 `01M6E2XXQNX1FYXPM37FGTYCKQ` | 1.8.0rc1 `3b2650a` | 12:14:46-12:17:07 | 3 | **stopped by its canary**: a product valid in the builder whose price its data states for no store (T01). Rejected, store held |
| Q1b `01M6E3RDEBPZ39SVR37JR6PE8F` | 1.8.0rc2 `b1d69d1` | 12:29:14-12:32:18 | 6 | **stopped as ABNORMAL_RESULT**: three pages in a row with products in the page state and none read as cards (T02, the new card variant). Rejected, store held |
| Q1c `01M6E49AHDXSQA04JQZ0HZ40GH` | 1.8.0rc3 `ec3b6fe` | 12:38:28-12:52:42 | 22 | rows 23-26 complete (Candles 52, Batteries 97, Light Bulbs 94, School Office 119): 362 products, 351 valid. Hard kill and resume. **Published** (local) |
| Q2 `01M6E5V6CASQ8F00VC8PE9TFYW` | 1.8.0rc4 `9d16475` | 13:05:42-14:10:40 | 85 | rows 22-27: 1,160 products, 1,137 valid. Planned kill, unplanned stop, automatic resume. **Rejected** (G3 Cat Food 231 of 232; G13, see T08). Last-good kept |

Targets of §13:

- **Achieved:**
  - the Vernon Hills store id and Pickup on every page;
  - more than 500 distinct valid fresh products from several categories (1,137 from 6 CSV rows);
  - successive pages processed live;
  - product and page source links on every record;
  - a real interruption and resume (two kills and a stop) and a repeat run (Q2 repeats Q1c's rows);
  - the last-good publication protected;
  - every segment's release recorded.
- **Not achieved:**
  - full required coverage (rows 0-21 not run, row 22 incomplete);
  - live retention of a product no longer seen (none disappeared);
  - live observation of the C02-C04 products.
- **Not counted as new collection:** Lakeshore East and the offline reprocessing of 1.7.0rc2's records.
- **Detail and offer links:** no product-detail page was requested. Product pages failed at the provider (L3, L16),
  so every field comes from the listing pages.
- **The walkthrough** records real commands as they ran, on Hamza's workstation (not the client's VM).
  - Parts 1 and 2 ([`walkthrough/WALKTHROUGH_1.8.0rc4_part1.webm`](../walkthrough/WALKTHROUGH_1.8.0rc4_part1.webm), [`walkthrough/WALKTHROUGH_1.8.0rc4_part2.webm`](../walkthrough/WALKTHROUGH_1.8.0rc4_part2.webm)) show Q2 on 1.8.0rc4: the
    planned kill, the unplanned stop, the resumes, the export and the checks.
  - Part 3 ([`walkthrough/WALKTHROUGH_1.8.0rc5_part3.webm`](../walkthrough/WALKTHROUGH_1.8.0rc5_part3.webm)), recorded afterwards, shows 1.8.0rc5 offline: its version, the G13
    regressions, the integrity re-check of the live data and the full suite's result.
  - It shows no live run of 1.8.0rc5 and no full category list. The recordings and each step's raw output are in
    [`evidence/walkthrough/`](../evidence/walkthrough/).

## 14. Releases and verification sequence

| Release | Commit | Change | Verification |
|---|---|---|---|
| 1.8.0rc1 | `3b2650a` | pagination loop, migration 0004, offers, sizes, conflict label, recovery order, coverage reconciliation, the Vernon Hills store | frozen **without a complete suite run** (my error): the full suite started 12:06Z was interrupted at 12% when the tree changed. It had one failure, a stale test expectation (the migration head after 0004), corrected afterwards: the migration tests pass from rc2 on |
| 1.8.0rc2 | `b1d69d1` | T01 PRICE_STORE_NOT_STATED | unit, replay and migration tests 434 passed. Full suite interrupted (superseded by rc3) |
| 1.8.0rc3 | `ec3b6fe` | T02 both card variants | unit and replay 433 passed. Full suite **interrupted** at 144 passed, 0 failed (superseded by rc4) |
| 1.8.0rc4 | `9d16475` | T03 export coverage files and version | targeted 503 passed. **Full suite from the clean extraction of its source archive: 574 passed in 25:33** ([`evidence/tests/t_full_rc4_x18.log`](../evidence/tests/t_full_rc4_x18.log)) |
| docs | `923afa4` | README, CLI, operations and Azure documents for 1.8.0. No code, test or configuration change (`git diff` empty on them) | – |
| **1.8.0rc5** | `ee5ec99` | T08: G13 no longer fails a run for a fetch that brought no page and that nothing in the run depends on. A missing or altered page the run depends on still fails it | the new regression **fails on rc4 and passes on rc5** ([`evidence/rc5-offline/t_rc5_tests_on_rc4.log`](../evidence/rc5-offline/t_rc5_tests_on_rc4.log)). Offline re-check of the real qualification database: rc4 reports Q2's page hashes as not verified, rc5 as verified, and Q1, Q1b and Q1c are verified under both ([`evidence/rc5-offline/integrity_q180_rc4_vs_rc5.txt`](../evidence/rc5-offline/integrity_q180_rc4_vs_rc5.txt)). Full suite: **576 passed in 26:02** from the clean extraction of its source archive, with the workstation held awake ([`evidence/rc5-offline/t_full_rc5_x19b.log`](../evidence/rc5-offline/t_full_rc5_x19b.log)). An earlier attempt ran through the workstation's standby and is void ([`evidence/rc5-offline/t_full_rc5_x19.log`](../evidence/rc5-offline/t_full_rc5_x19.log)): its one failure passed when run alone ([`evidence/rc5-offline/t_windowed_gap_rc5.log`](../evidence/rc5-offline/t_windowed_gap_rc5.log)) and again in the full rerun |

**The delivered package** was verified from a fresh extraction of its final archives, following the 12 steps of the
brief's §16 ([`evidence/verification/PACKAGE_VERIFICATION.txt`](../evidence/verification/PACKAGE_VERIFICATION.txt)):
- the steps: install, version agreement of source, wheel, CLI and documents, lint and types, unit tests, the
  regressions and the full suite again;
- the records against their stored pages, schema, counts, links and coverage;
- the PDF and the three videos;
- secret scans of every file and archive member;
- the earlier deliveries unchanged;
- checksums written last and read back.

This repository republishes the delivery file by file, without the archives and the PDF summary. What was moved,
corrected, redacted or left out is listed in `manifests/` (`FILE_MAP.csv`, `DOC_CORRECTIONS.md`, `REDACTIONS.csv`,
`EXCLUDED.csv`), and the checks of this publication are in `manifests/PUBLICATION.json`.

Void or interrupted test sessions, kept and reported:

- **Morning standby.** The workstation entered Modern Standby from 06:10:31Z to 11:49:19Z. Every session running
  across it is void.
- **Two sessions on one database** (my error). The morning's full suite and the last-good tests shared one test
  database, and one dropped the other's tables. Both were rerun separately.
- **Afternoon standby.** From 14:14:34Z the workstation was in Modern Standby, and its network was cut at 14:34:54Z
  until 15:11:11Z. The rc5 suite started at 14:23:30Z ran throttled: 72 tests in 50 minutes, one of them failed. I
  stopped it, and that session is **void** ([`evidence/rc5-offline/t_full_rc5_x19.log`](../evidence/rc5-offline/t_full_rc5_x19.log)).
  - The failed test passed alone on rc5 once the machine was awake ([`evidence/rc5-offline/t_windowed_gap_rc5.log`](../evidence/rc5-offline/t_windowed_gap_rc5.log)).
  - The suite was rerun from the same clean extraction.
- **Verification runs before the final one.** A rehearsal on a first clean extraction found document fixes; I
  stopped its full suite at 17:18Z on purpose, and it is not counted. A second complete run, started at 17:22Z,
  was superseded at 17:38Z, when the evidence archive was rebuilt after a wording correction (section 12); its
  full suite still finished: 576 passed (17:22-17:48Z). [`evidence/verification/PACKAGE_VERIFICATION.txt`](../evidence/verification/PACKAGE_VERIFICATION.txt) is the run on a third clean
  extraction.
- **Power requests.** Each long job now holds a Windows power request for its own duration (a workstation
  utility, not published), and no power setting is changed.

Other events:

- **A quoting error of mine** wrote Q1c's export to a wrong folder name. It was moved, and its manifest hash is
  identical to the run's own.
- **The census stage stopped once** for the same standby (section 5).

## 15. Evidence classes (brief §14)

| Class | In this delivery |
|---|---|
| 1. New live collection | Q1, Q1b, Q1c, Q2 at Vernon Hills Pickup (`evidence/live-runs/<run>/`); probes L1-L20; the department census |
| 2. Historical live evidence | 1.7.0rc2's runs and stored pages at Lakeshore East (`D170:`), used only for offline re-checks |
| 3. Offline replay | replay of stored Vernon Hills pages ([`source/tests/fixtures/oxylabs_2026-11-02/`](../source/tests/fixtures/oxylabs_2026-11-02/)); conflict trace; offer and size censuses; G13 re-check; the record check ([`evidence/tools/check_records.py`](../evidence/tools/check_records.py)) |
| 4. Synthetic and fault injection | the unit and integration suites; the synthetic `/pl/` site with worker kills, child listings and the brand-filter reading; the probe's synthetic rate card |
| 5. Azure execution | none in this task (client VM not executed; Hamza's VM not used) |
| 6. Untested or blocked | product pages (provider 500); price partitions; child-listing and brand-filter readings live (implemented, tested offline only); Classic (no credentials); client VM; full coverage |

Every record's chain is in its provenance: the CSV row, listing and page fetch, the page's SHA-256 and stored
document, the store and fulfillment from that page, then each field's observation and the exported value.
[`evidence/tools/check_records.py`](../evidence/tools/check_records.py) re-reads a random sample of records from their own stored pages.

**Sanitization.** Pages are stored after the collector's sanitizer (`sites/marianos/sanitize.py`). The original
evidence archive changed no file. For this public repository a few files were redacted (a workstation host name
and user folder, a key fingerprint, a request cookie echoed in one probe page, a key-handling note); each is listed
with both SHA-256 values in `manifests/REDACTIONS.csv`. No key, Authorization header or connection string is in
the delivery; the secret scans are in [`evidence/verification/PACKAGE_VERIFICATION.txt`](../evidence/verification/PACKAGE_VERIFICATION.txt) and `manifests/PUBLICATION.json`.

## 16. Open items and the smallest next authorized test

**Work remaining for the developer** (each live item needs an approved route and allowance, below):

1. **Full coverage at Vernon Hills Pickup:** rows 0-21, and the Cat Food gap (231 of 232).
   - Smallest test: one run of 1.8.0rc5 over one large department, under its own ceiling. It would be rc5's first
     live run and the first live use of the child-listing and brand-filter readings for categories above the window.
   - Before it, a probe of one category's brand pages would show whether its brand readings add up to the
     category's total. A category whose readings do not account for its total stays incomplete.
2. **Live re-observation of the C02-C04 products:** a run including Beer Wine Liquor and Deli at Vernon Hills.
3. **The client VM's offline checks** ([`ACCEPTANCE_RUNBOOK.md`](ACCEPTANCE_RUNBOOK.md) §2): Hamza loads the key once the VM is available.
4. **Open minor defects:** T05 (probe traceback), T06 (the run's own export shows its last segment without an end
   time), T07 (a provider-error pause is logged as `RUN_LIMIT_REACHED`).
5. **Mutation check:** the 3 mutants not run.
6. **Runtime of a full run:** with brand partitions the estimate exceeds one worker's time between twice-weekly
   runs ([`COST_AND_RUNTIME_REPORT.md`](COST_AND_RUNTIME_REPORT.md) §5). Concurrency is not verified.

**Access or decisions needed from the client:**

1. **The VM:** available (running) at an agreed time for the offline checks; its shutdown policy is the client's.
2. **Live work:** approval of a route, account and allowance for the runs above, and for any run on Azure.
3. **Classic:** approval, the account owner's credentials, entitlement and confirmed rates. Its live mode stays
   disabled until then.
4. **Schedules and publication:** schedules stay disabled, and no production publication target is set, until the
   client authorizes them.
5. **Acceptance:** the client's own checks of this delivery ([`ACCEPTANCE_RUNBOOK.md`](ACCEPTANCE_RUNBOOK.md)).
6. **The IP transfer and support terms:** still subject to agreement.

## 17. State at handover

- **Processes:** none of this task's is left running. The PostgreSQL server used for the qualification and test
  databases is stopped at the end of the verification, and so is the SSH agent prepared for the client's VM (it
  never held a key); no collector, test, recorder or browser process remains.
- **Schedules:** disabled in every configuration of this task (`schedule.enabled: false`). No Windows task, cron job,
  timer or Azure job was created.
- **Kept on Hamza's workstation for review (not part of the delivery):**
  - the qualification database `marianos_q180` (the four runs) and its data folder, unchanged since Q2;
  - the throwaway test databases in the same PostgreSQL data folder: `marianos_test` and the `marianos_test_*`
    databases, `marianos_mut`, `marianos_mut_test`, `marianos_old_test` and `marianos_probe`;
  - the task's working folder and the clean extractions used for the checks;
  - the task ledger, never reset.

  They can be removed after the review; nothing else uses them.
- **Provider accounts:**
  - Oxylabs Web API: 159 submissions in this task, USD 0.2160 at the reserve rate (our count, not an invoice).
    That makes USD 0.7899 of the USD 1.00 ceiling over the 1.6.0 to 1.8.0 tasks, so USD 0.2101 is left. No reservation
    is open.
  - Scrapfly, ZenRows and Scrape.do: no request in this task.
  - Kroger: 2 free certification-API requests (K1).
- **The client's VM:** no login, nothing run and nothing changed; the only contact was the host-key check of
  section 12. Its shutdown policy is untouched.
- **Repository:** the development branch `marianos-1.8` at `ee5ec99` stays local. This public repository holds
  its frozen tree and the evidence, added afterwards in a packaging commit (`manifests/PUBLICATION.json`). The Walmart project and its
  deliveries are untouched (checked: [`evidence/verification/PACKAGE_VERIFICATION.txt`](../evidence/verification/PACKAGE_VERIFICATION.txt), step "earlier").
- **External dependencies:**
  - the Oxylabs Web API, the only route verified live at Vernon Hills Pickup;
  - the structure of Mariano's site: the product-card variants and the `/pl/` window of 250 products.

Prepared by Hamza.
