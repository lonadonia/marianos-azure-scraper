# Cost and runtime: Mariano's collector 1.8.0rc5 (task 1.8.0, 2026-11-02), with release 1.9 (section 0, 2026-11-09)

All amounts are in USD. Each figure says what kind of number it is:

- **measured usage:** a count from a ledger (submissions, outcomes, times);
- **estimated cost:** a measured or estimated count times a stated rate;
- **list price:** a provider's published price, without discounts or tax;
- **account balance:** what the provider holds for the account. It is **not readable** with this key;
- **invoice:** none was read for this task.

Store for every live figure: Mariano's Vernon Hills 53100502, PICKUP. Ledgers: the task's own budget ledger
([`evidence/accounting/budget180.jsonl`](../evidence/accounting/budget180.jsonl), reserve before dispatch, append-only) and the collector's provider ledger in the
qualification database ([`evidence/accounting/REQUEST_LEDGER.csv`](../evidence/accounting/REQUEST_LEDGER.csv)). Both agree for every run.

## 0. Release 1.9 (2026-11-06 to 2026-11-09)

Sections 1 to 7 are the 1.8.0 report as published on 2026-11-02, unchanged. This section adds what release 1.9 spent
and measured, and what it changes in the estimates.

**One ledger for the trial credit of both projects.** Since 2026-11-03 Hamza's Oxylabs trial credit is governed by
one ledger for Walmart and Mariano's (campaign `oxylabs-trial-20261103`, the shared trial controller): USD 5.00 in
total for both, USD 0.50 kept as uncertainty headroom, envelopes of USD 2.25 per retailer. Every submission is
reserved at its worst case (USD 0.0015 per result) before it is sent, under an exclusive lease; an answered page is
settled at that rate, a provider failure documented as free at 0, and a submission without an answer stays held as
unknown at its worst case. A restart, a branch or a new configuration cannot open a second campaign. For this account
it replaces the per-task ceilings of §1. Read at 2026-11-09 17:34:54Z, hash chain verified (chain_ok true over 5,560 events):

| Ledger, USD at the reservation rate | Envelope | Settled | Unknown, held at worst case | Committed | Spendable |
|---|---|---|---|---|---|
| Campaign, both projects | cap 5.00; headroom 0.50; allocatable 4.50 | 2.6220 (1,748 results) | 0.0345 (23 submissions) | 2.6565 | **1.8435** |
| Walmart (its own tasks; not used by this one) | 2.25 | 2.2230 (1,482 results) | 0.0240 (16) | 2.2470 | 0.0030 |
| **Mariano's** (276 submissions) | 2.25 | 0.3990 (266 results; 3 submissions settled free) | 0.0105 (7) | 0.4095 | **1.8405** |
| of which 2026-11-06: O1, S1, O2 (28) | | 0.0390 (26 results; 2 free) | 0 | 0.0390 | |
| of which 2026-11-09: ten stages (248) | | 0.3600 (240 results; 1 free) | 0.0105 (7) | 0.3705 | |

"Settled" is measured usage times the reservation rate, the highest non-AI row of Oxylabs' published pricing ("Custom
domain, JS", USD 1.50 per 1,000 results, read 2026-11-03): a **list price used as a worst case**, not an invoice and
not a confirmed account rate. The account balance is still not readable with this key, and no invoice was read.

**Mariano's stages of release 1.9** (measured usage; every row in
[`evidence/1.9.0/budget/LEDGER_ROWS_MARIANOS.csv`](../evidence/1.9.0/budget/LEDGER_ROWS_MARIANOS.csv)):

| Stage | Started (UTC) | Revision | Submissions | Results settled | Settled free | Unknown, held | USD settled | USD held |
|---|---|---|---|---|---|---|---|---|
| O1, terms and offers | 2026-11-06 18:35 | requests by the stage tool | 16 | 14 | 2 | 0 | 0.0210 | 0 |
| S1, canary | 2026-11-06 19:33 | 1.9.0rc1 | 5 | 5 | 0 | 0 | 0.0075 | 0 |
| O2, tile discovery | 2026-11-06 19:45 | requests by the stage tool | 7 | 7 | 0 | 0 | 0.0105 | 0 |
| S1b, canary | 2026-11-09 12:36 | 1.9.0rc3 | 13 | 13 | 0 | 0 | 0.0195 | 0 |
| S4, rows 22-27 | 14:30 | 1.9.0rc3 | 43 | 43 | 0 | 0 | 0.0645 | 0 |
| S5a, rows 23-26, one lane | 14:41 | 1.9.0rc3 | 19 | 19 | 0 | 0 | 0.0285 | 0 |
| S5b, rows 23-26, two lanes | 14:46 | 1.9.0rc3 | 20 | 17 | 0 | 3 | 0.0255 | 0.0045 |
| S3, Milk | 14:56 | 1.9.0rc3 | 6 | 6 | 0 | 0 | 0.0090 | 0 |
| S5b2, rows 23-26, two lanes | 15:15 | 1.9.0rc4 | 17 | 13 | 0 | 4 | 0.0195 | 0.0060 |
| S4b, rows 22-27 | 15:52 | 1.9.0rc4 | 32 | 31 | 1 | 0 | 0.0465 | 0 |
| S4c, 31 listings of rows 1-21 | 16:00 | 1.9.0rc4 | 59 | 59 | 0 | 0 | 0.0885 | 0 |
| S3b, Frozen | 16:12 | 1.9.0rc4 | 4 | 4 | 0 | 0 | 0.0060 | 0 |
| S4d, 30 single-page listings | 16:20 | 1.9.0rc4 | 35 | 35 | 0 | 0 | 0.0525 | 0 |
| **All** | | | **276** | **266** | **3** | **7** | **0.3990** | **0.0105** |

No purchase, top-up, overage or other provider was used, and the client's account was not used. The stages of
2026-11-09 ran under Hamza's approval of at most 295 submissions and USD 0.4425; 248 were used.

**Latencies measured on 2026-11-09** (the provider's queue included; listing answers from the paging census, the
others from the stage logs):

| Request (2026-11-09) | Answers with a time | Median | Range |
|---|---|---|---|
| listing page, asked unrendered and brought unrendered | 187 | 5.1 s (90th percentile 8.9 s) | 2.9 to 52.1 s |
| listing page, asked unrendered and rendered by the provider anyway | 12 | 33.7 s | 27.5 to 45.7 s |
| the Coupons page (rendered every time) | 10 | 29.1 s | 13.3 to 88.7 s |
| product page asked rendered (S1b), rendered | 2 | | 16.7 and 25.4 s |
| product page asked rendered (S1b), brought unrendered | 6 | | 3.6 to 5.0 s |

Listing answers from the paging census ([`PAGING_CENSUS_190.csv`](../evidence/1.9.0/live/PAGING_CENSUS_190.csv)): 13 of the 202 asked unrendered were rendered by the provider, 12 of them with a time; 6 answers have no provider metadata (sessions ended by the hard kills of S5b and S5b2). The Coupons page from each run's `page_fetches` table, the product pages from S1b's log.

**What changes in the §5 estimate.** The submissions do not change: they count pages (scenario B, all rows, 3,928 to
6,277 a run, USD 5.89 to 9.41 at the reserve rate, about USD 51 to 82 a month twice weekly). The time per page does:
the 57.7 s per page of §5 was measured on rendered listing pages, and 1.9 reads them unrendered. One lane read
188 submissions (one of them a provider failure, settled free) in 1,931.7 s of active collection over the five one-lane runs S4, S5a, S4b, S4c and S4d (each run's `collection_segments` table): 10.3 s per submission, 8.7 to 12.7 by run; at that rate, scenario B would take about **11 to 18 hours** with one lane instead
of 48.4 to 77.3. **This is an extrapolation from five runs of 19 to 59 submissions, not a full run**, and it holds
only if the listings are answered in form A, with distinct later pages and the filters present (technical report
1.9.0 §3.2). Whether unrendered requests are billed below the reserve rate is not known.

**Product-page reads for coupon terms** (off by default) would add one submission per product read; with the tile
showing no coupon, every product is a candidate, and the provider rendered 1 of 14 product pages on 2026-11-06 and
2 of 8 on 2026-11-09.

**A re-ask of form-B answers** (proposed change C1, technical report 1.9.0 §15) would add at most 2 submissions per
answer it sets aside.

**The trial credit cannot hold the full scope.** Scenario B needs USD 5.89 to 9.41 a run at the reserve rate, against
USD 1.84 left in Mariano's envelope. The next proposed stages (S6, at most 130 submissions, USD 0.195; S6b,
at most 86, USD 0.129; S7, runs of at most 200 submissions, USD 0.30, within what Hamza approves;
[`evidence/1.9.0/budget/NEXT_STAGES.json`](../evidence/1.9.0/budget/NEXT_STAGES.json)) fit; a full-scope run is for the
client's account, after the client's decision.
## 1. Spending against the ceilings

| Account | Unit | Ceiling | Used in this task (measured) | Remaining |
|---|---|---|---|---|
| Oxylabs Web API, Hamza's account (key fingerprint not published) | submissions, USD at the reserve rate | stages: L 24 / 0.036, Q 200 / 0.30, D 24 / 0.036; **USD 1.00 for all Oxylabs products over the three tasks** | L 20 / 0.0225; Q 116 / 0.1590; D 23 / 0.0345: **159 submissions, USD 0.2160** | **USD 0.2101** of the 1.00 (1.6.0 and 1.7.0 used 0.5739) |
| Scrapfly | credits | 300 cumulative | 0 | 187 |
| Kroger API (certification host) | requests | 6 | 2 (free) | – |
| ZenRows, Scrape.do, Oxylabs Web Unblocker and Residential, Classic | – | – | not used | – |

- **The reserve rate.** USD 0.0015 per submission. It is above every rate on Oxylabs' pricing page as read in the
  1.7.0 task (from USD 0.50 per 1,000 results), so the ceilings stay conservative.
- **What a submission costs.** A submission the provider failed with HTTP 500 and "you can try again at no extra
  cost" is counted as free. A submission whose outcome is unknown (a time-out, a broken connection, or in flight at
  a forced stop) is counted as **possibly charged**, never reset.
- **No purchase**, plan change or budget reset was made.

## 2. Oxylabs in this task, reconciled

| Stage | Submissions | Answered | Free failures | Unknown (possibly charged) | USD, worst case |
|---|---|---|---|---|---|
| L: probes L1-L20 (05:00-05:30Z) | 20 | 13, plus the L1 404 caused by my tool (kept as charged) | 5 | 1 (L19 time-out) | 0.0225 |
| Q: runs Q1, Q1b, Q1c, Q2 (12:14-14:10Z) | 116 | 94 | 10 | 12 | 0.1590 |
| D: department census (14:34-15:24Z) | 23 | 20 | 0 | 3 (standby; section 5) | 0.0345 |
| **Total** | **159** | 127 (+1) | 15 | 16 | **0.2160** |

**By run in stage Q** ([`evidence/accounting/REQUEST_LEDGER.csv`](../evidence/accounting/REQUEST_LEDGER.csv)):

- Q1: 3 submissions, all answered.
- Q1b: 6, with 5 answered and 1 HTTP 502 of unknown cost.
- Q1c: 22, with 20 answered, 1 free HTTP 500 and 1 in flight at the planned kill.
- Q2: 85 submissions:
  - 66 answered;
  - 9 free HTTP 500;
  - 3 HTTP 502;
  - 2 connection time-outs;
  - 3 broken connections;
  - 2 in flight at the stops.

## 3. Cost per verified product (estimated cost)

| Measure | Value |
|---|---|
| Q2: 1,137 valid fresh products from 85 submissions, worst case USD 0.114 | **USD 0.10 per 1,000 valid products** |
| Q1c: 351 valid products from 22 submissions, worst case USD 0.0315 | USD 0.09 per 1,000 |
| Per listing page completed in Q2 (58 pages, 78 listing submissions) | 1.3 submissions, USD 0.002 at the reserve rate |

## 4. Runtime (measured)

| Run | Segments (active time) | What ran |
|---|---|---|
| Q1c (1.8.0rc3) | about 2 min to the planned kill; 11 min 34 s after the resume | 16 listing pages of rows 23-26 and the robots and Coupons reads: 22 submissions |
| Q2 (1.8.0rc4) | 7 min 19 s to the planned kill; 32 min 35 s to the unplanned stop; 17 min 9 s to the provider-error pause; 37 s after the automatic resume: **57 min 40 s in all** | 58 listing pages of rows 22-27, 2 empty listings, 85 submissions |

- **Answered submissions** waited 23.5 minutes in all. The median listing response took 10.0 s and the 90th
  percentile 67.1 s.
- **Submissions that brought no page** waited 31.2 minutes in all, between 6 s and 3 minutes each. Provider
  failures, not page counts, set the runtime.
- **Assembly, checks and export** after the last request took under 1 minute.
- **Memory and recovery.** The unplanned stop of Q2 came from the workstation's memory, not the collector. Each of
  the three forced stops was recovered by `resume`: no completed page was fetched again, and no product was recorded
  twice. The submission in flight at each stop was sent again after the resume, and failed submissions were
  retried; all of them are counted in the ledger.

## 5. The full required scope at Vernon Hills Pickup (twice weekly)

**Measured scope: the department census** ([`evidence/census/FULL_SCOPE_CENSUS.csv`](../evidence/census/FULL_SCOPE_CENSUS.csv), [`evidence/census/FULL_SCOPE_BY_CSV_ROW.csv`](../evidence/census/FULL_SCOPE_BY_CSV_ROW.csv),
[`evidence/census/FULL_SCOPE_ESTIMATE.json`](../evidence/census/FULL_SCOPE_ESTIMATE.json); test plan Amendments 8 and 9).

- **How.** One request per department page at 53100502 PICKUP, from 15:17 to 15:24Z. Each page states the
  department's product count and each category's count.
- **The first attempt was lost.** It started at 14:34Z, but the workstation was in Modern Standby: its network was
  cut at 14:34:54Z, and 3 submissions failed locally. They are settled as possibly charged.
- **Measured (17 departments):**
  - 16 departments from the census;
  - Breakfast from probe L15;
  - Health with its total only (2,291 products, no category list).
- **Not measured (4 departments):** Pantry (01), Beverages (04), Frozen (19) and Personal Care (21). Their pages came
  back with the site's search still loading (no counts). Following the plan, they were not retried.
- **Control:** the census's Pet categories add up to 755 listed products and 38 pages. Q2 read exactly 38 pages for
  row 22 at 13:13-13:40Z. The department total, 753, is 2 lower because 2 products are in both Cat Food and Cat Treats,
  as Q2 also found.

**What the measured part holds:** 158 categories named by the CSV rows' menu nodes (Health counted once, at its
department total), listing **19,911 products** (products in two categories counted in each). 20 of these categories are above the 250-product window, and they hold
11,034 of the products. Reading every one of them to its end takes **909 listing pages**.

**Two scenarios, both estimates:**

- **A, without brand partitions.** Every category is read page by page to its end, and a category above the
  window is read through its child listings. The work is about one page per 24 products.
  - Child listings that are themselves above the window would stay **incomplete**, for example cold cereal, with
    277 products.
  - The department pages do not say how many such leaves there are.
- **B, with brand partitions: the path 1.8.0rc5 takes.** Leaves above the window are divided by brand, the only
  retailer filter shown to work on `/pl/` (L20).
  - **The collector implements this** (`brand_partitions()`, since 1.8.0rc1, on by default) and it is tested
    offline. It has **not run live**, and whether the brand readings add up to each leaf's total is not shown.
  - Brand partitions multiply the pages: measured on stored pages, cold cereal needs 68 brand pages against 12,
    Cereal & Granola 81 against 17, and Breakfast as a whole 180 against 40. So the pages of the categories above the
    window are multiplied by **4.5 to 5.7**.

**The rates applied** (from Q2, measured):

- **Requests:** 1.3 submissions per page that counts (failures and retries included), plus about 3 per run
  (robots.txt for each segment and the Coupons page).
- **Time:** 57.7 s of run time per page, one worker in series.
- **Cost:** USD 0.0015 per submission, the reserve rate, worst case.
- **Cadence:** twice weekly is 8.67 runs a month.

**The unmeasured departments.** They are given a range: 1,000 to 3,000 listed products each. That is the range of the
measured large food departments: Dairy & Eggs 1,517, Meat & Seafood 1,338, Natural & Organic 2,811 and Produce
1,097. It adds 167 to 500 pages in A, and the same multiplied in B at the measured share of pages above the window
(52%). **This range is an assumption, not a measurement.**

| Scenario, per run | Listing pages | Submissions | USD per run (reserve rate) | Hours, one worker | USD per month, twice weekly |
|---|---|---|---|---|---|
| A, measured departments only | 909 | 1,185 | 1.78 | 14.6 | 15.4 |
| **A, all rows** (unmeasured range included) | **1,076-1,409** | **1,402-1,835** | **2.10-2.75** | **17.2-22.6** | **18.2-23.9** |
| B, measured departments only | 2,550-3,113 | 3,319-4,050 | 4.98-6.08 | 40.9-49.9 | 43.1-52.7 |
| **B, all rows** (unmeasured range included) | **3,019-4,826** | **3,928-6,277** | **5.89-9.41** | **48.4-77.3** | **51.1-81.6** |

**Reading the table:**

- **Scenario B is the estimate for 1.8.0rc5 as configured, and it does not fit safely with one worker.** 48 to 77
  hours a run would leave little or no time between runs. Concurrency would be needed, and it is **not verified in
  1.8.0**. In 1.7.0 it was measured only on first pages (R3). It would need bounded tests under one shared request
  and spending ledger.
- **Scenario A would fit a twice-weekly cadence with one worker:** about 17 to 23 hours a run, 3.5 days apart. But
  coverage would stay incomplete wherever a leaf listing is above the window, and it is not how 1.8.0rc5 is
  configured.
- **The cost is small against the time.** Even scenario B costs about USD 51 to 82 a month at the conservative
  reserve rate. Oxylabs' self-service plans start at USD 30 a month (pricing page read in the 1.7.0 task); whether a
  plan's rate applies to this source was not verified.
- **Not included:**
  - product-detail pages, which failed at the provider (L3, L16) and are not used: every field comes from the
    listing pages;
  - digital-coupon detail pages, since the Coupons page lists no products;
  - Classic, which has no confirmed rates.

## 6. Azure (list-price estimates)

The collector would run on a VM. The rates below are those of the 1.7.0 report for a Standard_D2ls_v7 with a P4 disk
and a static IPv4: VM USD 0.117/h, plus IPv4 and disk, makes about USD 0.129 per hour while running. The disk and
IPv4, about USD 8.93 a month, are billed even while deallocated.

| Use | Hours a month | USD a month |
|---|---|---|
| VM always on | 730 | about 94.3 |
| Deallocated between runs, scenario A | 149-196 | about 26-32 (compute at 0.117/h + 8.93) |
| Deallocated between runs, scenario B | 420-670 | about 58-87; close to always on |

These are list-price estimates, not an invoice. The client's own Azure prices and VM size may differ. Nothing ran on
the client's VM in this task.

## 7. Unknown, and how it would be measured

- **The account balance and invoices:** not readable with this key. Hamza's provider dashboard would show them.
- **The four unmeasured departments:** one more request each, sent at a quieter time, or their category pages.
- **Leaf listings above the window, and the brand-partition overhead:** a probe of one category's brand pages
  under its own ceiling. The collector's brand path is implemented and tested offline; it has not run live.
- **Concurrency:** a bounded test with two workers and one shared ledger.
