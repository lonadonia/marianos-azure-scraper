# Test plan for release 1.8.0 (Mariano's): written before any billable request of this task

Written 2026-11-02T05:20Z. Environment for every provider request: Hamza's workstation or Hamza's own Azure VM.
Never the client VM (offline checks only). Never the client's accounts.

## 1. Accounts and remaining cumulative allowance

| Account | Whose | Allowance | Used before this task | Left | Unit used here |
|---|---|---|---:|---:|---|
| Oxylabs Web API, Residential, Web Unblocker (one shared ceiling) | Hamza | USD 1.00 cumulative | USD 0.5739 | USD 0.4261 | USD 0.0015 reserved per submission: at most 284 submissions |
| Scrapfly | Hamza | 300 credits cumulative | 113 | 187 | credits |
| ZenRows | Hamza | 4,400 credits (trial period to 2026-11-29) | 68 | 4,332 | credits |
| Scrape.do | Hamza | 0 for this task (the 10 left belong to Walmart too) | n/a | 0 | not used |
| Kroger certification host | Hamza | free, bounded | n/a | 6 requests | lead for the store ID only, never production data |
| Oxylabs Classic | the client | no credentials, no approval | 0 | 0 | not executed |

The ledger `C:/m6/ledger/budget180.jsonl` carries the two earlier ledgers: nothing is reset. The Oxylabs Web API key on
file has fingerprint <key-fingerprint>. [Redacted for publication: a note on this key's handling.]

## 2. Hypotheses, each with a material reason (saved evidence reviewed first)

Already answered by saved evidence, so **not** re-sent: `run_js` + `page=2` (H13r, 24 cards, 0 new), `taxonomyId` on
the search page (H9, H10), `price_range` 0.00-2.99 at store 53100503 (H11, total unchanged), the retailer's data API
through the page endpoint and the generic endpoint (H1, H1b, faulted).

| ID | Request (Web API unless noted) | Hypothesis | Why it is new | Cost if served |
|---|---|---|---|---:|
| L0 | `GET /v1/scrapers`, `OPTIONS` of the three Mariano's endpoints | endpoint list and parameters still as documented | free discovery, 1 week old | 0 |
| K1 | Kroger certification locations near 60061, chain Mariano's | a free lead for the location ID | never asked for this store | 0 |
| L1 | search, query `cereal`, `store_id` 53100502, `pickup` | the store and fulfillment are honoured: page state shows 1720 N Milwaukee Ave, 60061, PICKUP; `sourceLocationId` 53100502 | new store, new fulfillment | 1 |
| L2 | `/pl/cereal-granola/03001` at 53100502 pickup | listing pages are still refused | new store and fulfillment | 1 |
| L3 | product endpoint for one UPC of L1 | product pages are still refused | new store and fulfillment | 1 |
| L4 | `/q/cereal` at 53100502 pickup (the retailer's route table lists `/q/:slug`) | another server-rendered route with its own product list | route never tried | 1 |
| L5 | `/pb/general-mills/cereal-granola/03001` (route table: `/pb/:brandSlug/:taxonomySlug/:taxonomyId`) | a brand-and-taxonomy route is served | route never tried | 1 |
| L6 | `/search?page=2&fulfillment=all` without a query | the retailer's failed request, in the page state, shows the `page.offset` its server asked for (decides whether `page=2` is lost before the retailer's data service) | the H9 failure showed `page.offset: 0` for page 1 | 1 |
| L7 | search with the documented example form `price_range` `2.00-5.00` | the filter acts when the lower bound is not 0 | H11 used 0.00 | 1 |
| L8 | search `cereal` + `brand` of the most common brand at the store | the brand filter narrows the total at the store (a retailer filter, earlier seen at 53100503) | new store and fulfillment | 1 |
| L9 | `/search?query=cereal&searchType=default_search&sort=price&order=asc`-style form only if a saved page shows the retailer's own parameter names | a retailer sort reaches other products | only if evidence names the parameter; otherwise not sent | 1 |

At most 12 Oxylabs submissions for this stage. No retries, except one for `REQUEST_FAILED_SCRAPE_TIMEOUT`, which the
provider asks for and which is recorded.

## 3. Collector qualification, only after the corrections are committed and frozen

Vernon Hills PICKUP, Oxylabs Web API, the frozen 1.8.0 candidate, an isolated database, a stated submission ceiling.
At most 200 submissions, USD 0.30 at the reserve rate. One interruption and resume, one repeat. It may run only if L1
proves the store and fulfillment. If only first pages are served the report says so: first pages and any partition
route are never presented as category coverage. A browser route (Scrapfly, at most 120 credits in one session, the one
configuration that was served before) is tried only with a stated reason and is stopped on the first refusal.

## 4. Stop conditions

- A wrong store or fulfillment: stop the route, keep the evidence, no fallback to a default store.
- An explicit refusal, block or challenge: stop that configuration. No identity rotation, no challenge solving, no retry
  without a material change.
- Three provider failures in a row on one route: stop that route.
- The ledger refuses: nothing is sent.
- Any sign of a charge the ledger did not expect: stop and reconcile.
- The client VM is never given a provider credential or used for a request to a provider or the retailer.

## 5. Shutdown

No provider session stays open. Any database, scratch folder or process created here is listed at handover. Schedules
stay disabled. Nothing is sent to the client or to a provider's support.

## 6. Amendment 1 (2026-11-02T05:08Z, before L10): stage L raised from 12 to 24 submissions (USD 0.036)

L1 was sent twice (the first attempt never reached the scraper: Git Bash rewrote the endpoint path, HTTP 404 at the
provider's front door, kept in the ledger at the reserve rate). L2 and L9 changed the picture: `/pl/` listings are
served at 53100502 PICKUP and `?page=2` returns new products, so the following are new hypotheses, not retries.

| ID | Request | Hypothesis |
|---|---|---|
| L10 | `/pl/cereal-granola/03001?page=2` with `run_js` | the rendered page 2 shows product cards in the grid, the same as page 1 |
| L11 | `/pl/cold-cereal/0300100001` | a child listing named by the retailer's own `productsInfo.departments` is served |
| L12 | `/pl/cereal-granola/03001?page=11` | the last page inside the 250 window (offset 240) answers |
| L13 | `/pl/cereal-granola/03001?page=12` | what the source does past its window |
| L14 | a price-bucket filter on the child listing, using the retailer's own slug | a retailer filter narrows a listing above the window |
| L15 | one `/d/` department page of the client's CSV | the department route is served and names its children |
| L16 | one `/p/<slug>/<upc>` product page through the page endpoint | product pages are served with store and pickup context |
| L17 | the Coupons page of the CSV with `run_js` at 53100502 pickup | coupon cards for this store and fulfillment |
| L18 | `/search?query=cereal&searchType=default_search&page=2` at 53100502 pickup | whether `/search` still repeats page 1 here (the `/pl/` route does not) |

The cumulative ceiling is unchanged: USD 0.4156 left before L9, 20 of the 24 at most reserve USD 0.03.


## 7. Amendment 2 (2026-11-02), inside the L stage's ceiling

Results that led to it: L14 (`priceBuckets=5.0-7.49` on a listing above the window) failed at the provider, free; the page state gives
the bucket's slug as `5-0-7-49`, so L14 did not test the retailer's own value. L8 proved `brandName` on `/search` only.

| ID | Request | Hypothesis | Decides |
|----|---------|------------|---------|
| L19 | `/pl/cold-cereal/0300100001?priceBuckets=5-0-7-49` at 53100502 pickup | the slug the page state gives narrows a listing above the 250 window | whether a retailer filter can subdivide a leaf listing |
| L20 | `/pl/cold-cereal/0300100001?brandName=General%20Mills` at 53100502 pickup | the brand filter works on `/pl/` | same, for brand facets |

Stop: one submission each, no retry. Failed or ignored filter: leaf listings above the window stay "accessible pages exhausted; coverage incomplete".

## 8. Amendment 3 (2026-11-02T12:13Z, before stage Q's first request): the collector qualification

What section 3 left open is fixed here, before anything is sent.

- **Account.** Hamza's Oxylabs Web API, key fingerprint <key-fingerprint> [redacted for publication: a note on this
  key's handling]. Not the client's account, not Oxylabs Classic.
- **Environment.** Hamza's workstation (Windows 11). A clean detached worktree of the frozen candidate
  3b2650a0ffad65ea72fe853276463a6cc39c348f at `C:/m6/qwt`, its environment installed from the lock offline
  (`uv sync --frozen --offline`); the run records the git revision itself. PostgreSQL from pgserver on 127.0.0.1, a
  new database `marianos_q180` used for nothing else; data folder `C:/m6/q180/data`; configuration copy
  `C:/m6/q180/config`. Not the client VM, not Hamza's VM. No schedule: each execution is started by hand.
- **Remaining cumulative allowance.** Oxylabs USD 0.4036 of USD 1.00 before this stage. Stage Q reserves USD 0.30
  (200 submissions at the reserve rate USD 0.0015) in `budget180` before the first request, and the collector's own
  ledger gets the same ceiling (`set-ceiling --submissions 200 --usd 0.30`). At most USD 0.1036 stays after it.
- **Scope.** Store 53100502 (Vernon Hills, 1720 N Milwaukee Ave, 60061), PICKUP. CSV rows 23 Candles Home
  Fragrances (32001), 24 Batteries (26003), 25 Light Bulbs (26002), 26 School Office (35), plus the Coupons page and
  robots.txt that every run or session reads through the provider. This is a **qualification scope, not full
  coverage**: the other rows of the client's CSV are not collected and nothing from this stage is presented as the
  store's coverage. Row 27 is not added.
- **Per-run cap.** `max_credits_per_run: 95` (Oxylabs submissions), so that run Q1 with its resume and the repeat
  run Q2 fit in 200.
- **Sequence.** Q1: a new run of the scope. While a listing is being read, after at least one listing page is
  checkpointed, the collector process is killed hard (`taskkill /F`, the case of a VM that stops). `status`, then
  `resume` of the same run to its end; publication by the gates (automatic) or the recorded reason it is withheld.
  Q2: the same scope as a new run (the repeat). `export` and `validate-export` for each run. The ledger rows of both
  runs are compared with `budget180` and settled there.
- **Stop conditions.** Section 4, plus: the 200 / USD 0.30 ceiling; any page of the wrong store or fulfillment
  (the run stops without fallback and the stage ends); a refusal or block ends the stage; three provider failures in
  a row end the stage; if Q1 stops at its per-run cap with coverage incomplete, Q2 is not given a larger cap and the
  report says so; a difference between the collector's provider ledger and `budget180` stops the stage until
  reconciled.

## 9. Amendment 4 (2026-11-02T12:29Z): Q1 stopped at the canary; a corrected candidate; the stage goes on inside Amendment 3

**What happened.** Run Q1 (01M6E2XXQNX1FYXPM37FGTYCKQ, 1.8.0rc1 at 3b2650a) sent 3 submissions (robots.txt,
Candles page 1, the Coupons page) and stopped itself at the canary (CANARY_CHECK_FAILED, rejected, store held):
UPC 0019798100139 shows $8.69 while its own data states that price for no store (no
`price.storePrices.sourceLocationId`; the price is under `postalCodes` for 60061; stock TEMPORARILY_OUT_OF_STOCK).
The record builder had counted it valid; the canary's source check was right. Not a provider problem.

**Material change.** 1.8.0rc2 (b1d69d1004f7b8f8457d90c7c5d9f378be9fddfd): such a record keeps its displayed price,
is flagged PRICE_STORE_NOT_STATED and is never valid; the canary and the source check are unchanged. Replay of Q1's
stored page: 23 valid, 1 flagged, the canary passes. The clean worktree `C:/m6/qwt` is moved to b1d69d1 (its
environment re-synced from the lock, offline).

**What follows, inside Amendment 3's ceiling** (197 submissions and USD 0.2955 left of 200 / USD 0.30; the
per-run cap of 95 and every stop condition unchanged): `release-hold` of 53100502 Pickup in `marianos_q180` with this
reason; Q1b, a new run of the same scope from b1d69d1, with the planned hard kill and resume; then Q2, the repeat.
Q1's evidence stays in the database and its data folder. If Q1b stops at the canary again, the stage stops.

## 10. Amendment 5 (2026-11-02T12:38Z): Q1b stopped on three grid-less pages; a corrected candidate; the stage goes on

**What happened.** Run Q1b (01M6E3RDEBPZ39SVR37JR6PE8F, 1.8.0rc2 at b1d69d1) sent 6 submissions (robots.txt, Candles
page 1, Coupons with 24 coupon cards, Batteries page 1, Candles page 1 again) and stopped as ABNORMAL_RESULT
(rejected, store held) after three pages in a row whose page state lists the products while the parser saw no grid
card. The stored pages hold the 24 (Candles) and the Batteries products as `mini-product-card-N` cards (class
MiniProductCard) instead of `product-card-N`: a card variant the site served from about 12:30Z. The protection
worked; the parser was behind the site. Not a provider problem. The collector's ledger: 9 submissions, USD 0.0135 at
the reserve rate, 1 of them "unknown" (kept as possibly charged).

**Material change.** 1.8.0rc3 (ec3b6fe4f8ed3bb9a10a0eef2116a03cf9f45a61) reads both card variants; on Candles page 1
the 24 cards of both read the same field by field (replay test on the stored pages). `C:/m6/qwt` moved to ec3b6fe.

**What follows, inside Amendment 3's ceiling** (191 submissions and USD 0.2865 left of 200 / USD 0.30; the per-run
cap of 95 and every stop condition unchanged): `release-hold` with this reason; Q1c, a new run of the same scope
from ec3b6fe, with the planned hard kill and resume; then Q2, the repeat. If Q1c stops on the same kind of problem
again, the stage stops and the report says why.

## 11. Amendment 6 (2026-11-02T13:01Z, before Q2's first request): Q1c's result, release 1.8.0rc4, Q2's scope

**Q1c** (01M6E49AHDXSQA04JQZ0HZ40GH, 1.8.0rc3 at ec3b6fe): canary passed; hard kill at 12:40:33Z while Candles page 3
was in flight (`taskkill /F /T`), `status`, `resume` at 12:41:08Z (segment 01M6E4E725D256GG6YH7VX1ZCJ); the in-flight
submission was settled `unknown` (possibly charged) by the recovery, not left reserved. Rows 23-26 read to their end:
Candles 52 of 52, Batteries 97 of 97, Light Bulbs 94 of 94, School Office 119 of 119 (16 listing pages completed,
`?page=2..5`). 362 products, 351 valid; validated and published to the isolated local target of this stage
(`C:/m6/q180/data/published`), nowhere else. 22 submissions (one provider HTTP 500, settled free by the collector's
rule; one interrupted, settled unknown). Ledger after Q1c: 31 submissions, USD 0.0450 at the reserve rate (USD 0.0465
if the HTTP 500 was charged); 169 submissions and USD 0.2535 of the 200 / USD 0.30 stay.

**Material change.** Q1c's own export showed two defects: its manifest listed the four coverage files with their
SHA-256 but `export` and the manifest check never read them back, and its collector version said 1.7.0.
1.8.0rc4 (9d16475470a480b148823e30a07ec11c3e5184d6) reads them back and copies them, and records 1.8.0. The tests that show both fail on
1.8.0rc3 and pass on 1.8.0rc4. No collection, parsing or gate behaviour changed. `C:/m6/qwt` moves to 1.8.0rc4.

**Q2** (the repeat, from 1.8.0rc4): CSV rows 22 Pet Supplies (a department row: its menu listings), 23-26 (Q1c's rows,
the repeat) and 27 Hardware Home Improvement. Rows 22 and 27 are added because Q1c's four rows hold 362 products,
below the 500 valid fresh products the brief asks one run to show; this is still a **qualification scope, not
coverage**. The per-run cap stays 95 submissions and every stop condition of Amendment 3 stays; a cap reached is a
stop, never a complete run. Q2 is hard-killed once (after its fourth collected page step, while the next page is in
flight) and resumed, so that the final release is interrupted and resumed live too. The whole of Q2, with its kill,
resume, export and checks, is recorded as the walkthrough (asciinema recording of the real commands, rendered to
video). Q1c's publication is the last-good dataset during Q2.

## 12. Amendment 7 (2026-11-02T13:51Z, before Q2's next request): an unplanned second stop of Q2

**What happened.** Q2 (01M6E5V6CASQ8F00VC8PE9TFYW, 1.8.0rc4) was hard-killed as planned at 13:13:01Z and resumed at
13:13:08Z (segment 01M6E68TKYD7GG6DEXR8AWVEZ8). At about 13:45:43Z the workstation ran short of memory (a web browser
opened for a sign-in took about 3.5 GB) and the tool that ran the recording stopped its background tasks: the recorder
and, with it, the collector (no termination signal reached the collector; nothing was written after its last page
step, School Office page step 3, 13:45:43.994Z). Row 22 Pet Supplies and rows 23-25 were read before the stop; row 26
was at its fourth page and row 27 not started. The run stays `running`, its segment open, one listing submission
`reserved` (in flight or not yet sent). Q2 has 71 submissions, USD 0.1035 at the reserve rate; the ledger holds 102
of the 200 submissions and USD 0.1485 of the USD 0.30 (11 settlements of unknown cost, kept as possibly charged).

**What follows.** This is a second, unplanned forced stop; it is reported as such, never as planned. Q2 is resumed
once more from the same release (1.8.0rc4, `C:/m6/qwt`) with `resume`, whose recovery must close the open segment as
abandoned and settle the reserved submission as unknown (possibly charged), as it did at 13:13:08Z. No limit changes:
the per-run cap stays 95 submissions (24 left), the ceiling stays 200 / USD 0.30, every stop condition of Amendment 3
stays. If the cap stops the run, Q2 is finalized as a partial run (never published) and reported as such. The
recording goes on as a second part (WALKTHROUGH part 2, recorded in the same way); its first lines say that part 1
was cut by this stop. No background test or other heavy process runs while the collector runs.


## 13. Amendment 8 (2026-11-02T14:34Z, before stage D's first request): a department census for the full-scope estimate

**Why.** Q2 measured pages, requests and time for rows 22-27 only. The brief asks for a production estimate that
covers every required category and page, and for each CSV row to be reconciled to the retailer's categories with
their reported totals. A department listing (`/pl/<slug>/<2-digit id>`) states the department's product count and
its categories' counts at the requested store and fulfillment (L15, 05:15Z: Breakfast 03, 949 products, availableCount
250). Rows 1-22 of the client's CSV name menu nodes in 21 departments (`config/taxonomy_seed.snapshot_2026-10-17.json`);
Breakfast is already measured.

**Hypothesis.** Each department page answers at 53100502 PICKUP with the department's total and the counts of its
categories. Decides: the number of listing pages a full run needs, which categories exceed the 250 window, and the
estimated requests, cost and runtime per twice-weekly run.

**Requests.** At most 20 submissions, one per department, sequential, no retry: 27 pet first (control: its category
counts are compared with Q2's reported totals of 13:13-13:40Z), then 40 with an assumed slug (the name of department
40 is not known: this request also tests whether the slug is cosmetic), then the 11 departments whose slug the stored
pages give, then 7 departments with assumed slugs only if request 2 showed that the slug is cosmetic. Hamza's Oxylabs
Web API (key fingerprint <key-fingerprint>), from the workstation, through `probe180.py` (reserve before dispatch,
sanitized page kept, no key or header written). Not the collector, not the client VM, no schedule.

**Ceiling.** New ledger stage `OXP/D`: 24 submissions / USD 0.036 at the reserve rate (Oxylabs cumulative before it:
USD 0.2446 left of USD 1.00; at most USD 0.2086 after it).

**Stops.** A refusal or block ends the stage; any page of another store or fulfillment ends it; three provider
failures in a row end it; a failed department stays "not measured" (no retry). The census is not collection: no
product of these pages enters any dataset, and nothing from it is presented as coverage.

## 14. Amendment 9 (2026-11-02T15:17Z, before stage D's next request): the census continued after a local outage

**What happened.** Stage D's runner started at 14:34:35Z. Its first request (D27) waited 937 s and ended in a transport
error (RemoteProtocolError) at 14:50:12Z; D40 and D01 failed in 1-3 s (ConnectError, no connection made); the
runner stopped on its rule (three failures in a row). The workstation's System log shows the cause: Modern Standby
from 14:14:34Z, network disconnected at 14:34:54Z ("Adaptive Connected Standby"), a brief exit and re-entry at
14:50:12Z (network disconnected again 14:50:23Z, "Policy Setting"), exit at 15:11:11Z. The failures were local; no
answer from the provider was received. The three submissions stay in the ledger settled as possibly charged (never
reset). The full test suite running at the same time is void for the same reason (reported, rerun).

**What follows.** The same plan resumes from its first department (D27), inside the same ceiling (21 of the 24
submissions and USD 0.0315 of USD 0.036 left), with the same stops. Each long job now holds a Windows power request for
its own duration (`C:/m6/tools/awake_run.py`; no power setting is changed). If the stage stops again, it is not
resumed; departments not measured stay "not measured" in the estimate.
