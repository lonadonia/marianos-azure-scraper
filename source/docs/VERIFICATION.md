# Verification report: marianos-azure-headless 1.2.1

Prepared 2026-10-24 on the Windows workstation (Python 3.12, uv, PostgreSQL through `pgserver`, Playwright
Chromium for the tests). Release 1.2.1 is the commit this file belongs to. **No live run was made for this
release**: the campaign's credit allowance left 165 credits (ceiling 880 of the account's 1,000, 120 always
kept; 715 consumed), and a new browser session costs about 176 credits before its first product (store
selection, measured on 2026-10-23), so no continuation fits (COSTS in the delivery). The live data of the
delivery is therefore still run `01M5NAQKQ0H28DCGK5BE8XCP2N` of 2026-10-23 (section of 1.2.0 below),
re-checked offline. Evidence classes are never mixed: **offline** (synthetic pages, saved captures), **live**,
**container**, **Azure**.

## 1. Offline checks

Unit and integration suites, `ruff`, strict `mypy`, the CLI and the Bicep template; the delivery's package
verification repeats them from a clean extraction and states the counts. New in 1.2.1, each with a
regression test:

* `validate-export` reads a second evidence class, the product data embedded in the stored page copies
  (`window.__INITIAL_STATE__`), beside the product responses; results name their class (`by_evidence`).
  Product responses are preferred; a price or store difference with either is a mismatch.
* A listing whose total exceeds the site's result window is read through the child listings the site's
  category facet names (OPERATIONS.md, The site's result window): complete only when the distinct products
  reach the listing's total; otherwise INCOMPLETE with the gap (mock site: a covered listing and one with a
  gap). Not verified live.
* A challenge (a CAPTCHA frame, an interstitial, an access denial) that covers the Load More button is never
  clicked through: the page is checked before Escape or the click through the page, and the run stops as a
  site refusal with the page copy kept (mock site with a CAPTCHA layer).
* Retention: a product read through a child listing is carried forward under the client's listing it stands
  for, with the child named (`read_through`), whichever way a later run reads that listing (found in this
  review: the reason named the child as "not read" when a later run read the listing directly).
* Stock level: the parser also reads the live shape of 2026-10-23, `inventorySummaries[]` (the stock per
  fulfillment type and store; the In Store level counts). It read only `inventory.locations[]`, which some
  products' responses no longer carried, so 93 of the 183 products both Crackers runs saw have no stock level
  in their supporting log (found in this review; no exported field is affected; the delivery's availability
  report reads the level from the stored responses).

## 2. Live evidence re-checked offline (no credit spent)

`validate-export --run 01M5NAQKQ0H28DCGK5BE8XCP2N` with this release: 498 records; **497 equal to the site's
product data** (478 against product responses, 19 against the product data embedded in their stored page
copies: the Yogurt page step whose product responses were not captured), **1 conflict**, 0 unverified. The
conflict: UPC 0004119211060 (Kellogg's Honey Smacks), whose card showed "Sale: $5.49 discounted from $8.78"
(page copy of 21:55:13 UTC) while the product response of 21:55:20 UTC states regular $8.79 and promotion
$5.49; the export keeps the displayed $8.78 and the record is reported as a conflict, not as agreement.
Exit 6 because of that one record.

## 3. Container: NOT TESTED

No Docker on the preparation workstation.

## 4. Azure: DEFERRED (by Hamza for this task; not a client waiver)

Azure execution, Azure scheduling and the walkthrough video were deferred by Hamza for this task. This is not
a client waiver. Schedules stay off. The Bicep template builds; that is not a deployment.

---

# Earlier report: marianos-azure-headless 1.2.0

Prepared 2026-10-23 on the Windows workstation (Python 3.12, uv, PostgreSQL through `pgserver`, Playwright
Chromium for the tests). Release 1.2.0 is the commit this file belongs to. The live run below executed on
two earlier commits of the same release line, each recorded by its segment (`SEGMENT_STARTED`): segment 1
on `ab42275` (the frozen candidate), segment 2 on `ae75f6a` (adds the Load More click fallback found
necessary by segment 1). The release commit then adds the result-window status of a listing, the delivered
`browser_os: null` and `bandwidth_overhead_factor: 2.0` (both from the live measurements) and these
documents; none of these changes what the run collected. Evidence classes are never mixed: **offline**
(synthetic pages, saved captures), **live** (Scrapfly cloud browser sessions from the workstation to
marianos.com), **container**, **Azure**.

## 1. Offline checks

Unit and integration suites, `ruff`, strict `mypy`, the CLI and the Bicep template; the counts of the
release are in the delivery's package verification (from a clean extraction). New in 1.2.0, each with a
regression test: `products_fresh.json`/`.csv` (only what the run observed) beside the retained
`products.json`; per-record page copy and SHA-256 and the code version in `provenance.json`; the code of
each execution segment; `validate-export` checks carried-forward records against their own run's
responses and the fresh file against the retained one; a covered Load More button is clicked through the
page instead of failing the listing (mock site with a covering layer); a listing whose Load More ends at
the site's result window is INCOMPLETE with the site's numbers, not DONE; the provider's `os` parameter;
four unused settings that read like limits removed.

## 2. Live check of 2026-10-23 (workstation, not Azure)

Store 53100503 Marianos Lakeshore East, 333 E Benton Pl, Chicago, IL 60601, In Store. Scrapfly key
`…fe16cf` (a new FREE account: 1,000 credits; 1,000 → 285 over this check, read from the provider's
Account API). Campaign budget: at most 880 credits, 120 always left on the account.

| Item | Result |
|---|---|
| Run | `01M5NAQKQ0H28DCGK5BE8XCP2N`: rows 7 Grocery › Crackers (01026), 8 Dairy › Yogurt (02009), 12 Breakfast › Cereal & Granola (03001); explicit pilot limit 560 products |
| Fresh products | **492 verified, distinct, observed by this run** (Crackers 244, Yogurt 19, Cereal 229), plus 6 carried forward from run `01M5MHSN…` (14:14 UTC), labelled as such: 498 rows. **The 500 target was not reached.** |
| Store and fulfillment | the site's picker selected the store in each browser session; 29 store attestations, all PASS (every page step: location ID, name, address, ZIP, In Store, the store of every product request) |
| Interruption and recovery | Ctrl+Break after page step 16 (exit 75, browser close not confirmed: the signal also stopped Playwright's driver); a second run refused (exit 9); resume with a concurrent resume refused (exit 9); the resume opened a new session, selected and verified the store again, replayed the interrupted listing's steps without counting a product twice, finished the listing |
| Exports | contract passed for `products.json` (498) and `products_fresh.json` (492); 0 duplicate UPCs or URLs; PPM on 498 (oz 469, each 27, lb 2); sale price 254; volume offer 181 (13 with a displayed price); digital 0 |
| Source check (`validate-export`) | 478 records equal to the site's product data, 19 unverified (the Yogurt page captured no product data), 1 differs: the card shows "discounted from $8.78" while the site's data says $8.79 (exported as displayed). Exit 6 because of that one. |
| Publication | refused: a pilot dataset is never published |
| Platform hypothesis | `os=macos` requested; the provider's browsers reported Linux, then Windows; both served. Not supported; the 403 trigger stays unidentified (DIAGNOSIS_403.md) |
| Defects found live | (1) a Load More click timed out on a visible, enabled button; the error failed the Yogurt task after its first page step (fixed in `ae75f6a`); (2) every products-search response stated `availableCount` 250: Cereal reported 328 results, Yogurt 386, Crackers 254, and Load More ended at the window; the run labelled Cereal DONE (fixed in 1.2.0: INCOMPLETE with the site's numbers). The coverage check rejected the run either way. |
| Repeat of the Crackers scope | against run `01M5MHSN…` (same listing 7 h earlier, earlier collector revision and account): 183 products in both, 0 changed values; stock level per the site's product data: 2 HIGH → TEMPORARILY_OUT_OF_STOCK, 2 LOW → TEMPORARILY_OUT_OF_STOCK, 2 HIGH → LOW, all still listed, priced and kept; 6 not shown and carried forward |
| Credits | 420 (segment 1) + 295 (segment 2) = 715 measured; the collector estimated 353 and 332 (billed / measured traffic about 1.9 and 1.8) |

## 3. Container: NOT TESTED

No Docker on the preparation workstation.

## 4. Azure: DEFERRED

Azure execution and scheduling were deferred by Hamza for this task; schedules stay off. The Bicep template
builds; that is not a deployment. (Corrected in 1.2.1: this paragraph said the deferral was the client's
instruction. It was not; it is not a client waiver.)

---

# Earlier report: marianos-azure-headless 1.1.0

Prepared 2026-10-23 on a Windows workstation (Python 3.12, uv, PostgreSQL through `pgserver`, Playwright
Chromium for the tests). Release 1.1.0 is the commit this file belongs to. The final delivery
`marianos-final-<timestamp>-1.1.0` holds the evidence named here (`reports/`, `evidence/`) and maps every
live run to its source commit (`SOURCE_VERSION.json`); its package verification repeats the offline checks
from a clean extraction. Evidence classes are never mixed: **offline**, **live** (real cloud browser
sessions through Scrapfly from the workstation), **container**, **Azure**.

## 1. Offline checks

Unit and integration suites, `ruff`, strict `mypy`, the CLI and the Bicep template, rerun on the release
from a clean extraction (the delivery's package verification states the counts). New in 1.1.0:
publication safety on the real pipeline (synthetic mock site, local Chromium): a run stopped and
finalized, refused by the site, shown for another store, empty or thin never replaces the published
dataset; an interrupted publication is retried once, atomically. These tests found a defect, fixed in this
release: the abnormal-yield check had no baseline, so a thin run filled by carried-forward products could
be published. Also new: continuation across executions, the five CSV rows that are listing pages, and the
exit code of a finished run.

Workstation note: from about 18:00 UTC on 2026-10-23, Windows Application Control on the preparation
workstation blocked compiled modules it had allowed before (psycopg's `pq.pyd`, mypy's `librt`). Checks
after that ran with psycopg's pure-Python implementation and the `libpq.dll` shipped inside pgserver
(`PSYCOPG_IMPL=python`), and with mypy 1.18.2 built from source. This is a property of that workstation.

## 2. Live checks of 2026-10-23 (workstation, not Azure)

Store #53100503 Lakeshore East, In Store, through Scrapfly's Cloud Browser.

| Run | Result |
|---|---|
| `01M5MHSNT1TMXDHQVQZQCPP096` | **189 fresh verified products** (Grocery › Crackers): store selected with the site's picker and verified in each session, canary source check 20 of 20; Ctrl+Break after 8 page steps, a second run and a concurrent resume refused (exit 9), resumed as the same run in a new session (store verified again, nothing recorded twice), then stopped at its credit budget and finalized as partial; 520 credits |
| `01M5MERNPYEKA7MBK1B8M17884`, `01M5MJ67AKHN74AK5PQDG8YEGM` | refused by the site on the first listing page (HTTP 403 "Access Denied", Akamai reference): stopped, store held, nothing published |

The 500-product demonstration was not reached: the site refused 2 of 3 session starts and the trial
credits ran low (1,000 to 375). The trigger of the refusals is not established.

## 3. Container: NOT TESTED

No Docker on the preparation workstation.

## 4. Azure: NOT VERIFIED

No Azure access or deployment authorization was available. The Bicep template builds and lints; that is
not a deployment.

---

# Earlier report: marianos-azure-headless 1.0.0 (2026-10-22)

Prepared 2026-10-22 on a Windows workstation (Python 3.12.15, uv 0.13.1, PostgreSQL through `pgserver`,
Playwright 1.63.0 with a local Chromium for the mock-site tests). Source revision: the commit this file
belongs to. Code verified at commit `2b29aa0` (the Mariano's code is unchanged since `9ddd6f7`). Derived
from mscraper 1.2.6 (`f9c03085`). Evidence is kept in four classes that are never mixed: **offline**
(synthetic or captured inputs, no network), **live** (real requests to Scrapfly and Mariano's, from the
workstation), **container** and **Azure**. The delivery's `MARIANOS_TEST_EVIDENCE.zip` holds the live
runs' logs, sanitized page captures and site responses, screenshots, database rows, reports and terminal
screenshots.

## 1. Offline checks: PASS

`pytest` at `2b29aa0`, run in two groups (memory): **267 passed** (unit 230, integration
37), 0 failed, 0 skipped. `ruff check` and `ruff format --check` clean; `mypy --strict`
clean with mypy 1.19.1 installed from source (`uv run --with "mypy==1.19.1" --no-binary-package mypy
mypy`): the workstation's application control blocks the compiled mypy wheels' native modules. Database
tests use a throwaway PostgreSQL. Browser tests use a local Chromium over CDP, standing in for Scrapfly's
cloud browser, against a local mock site serving SYNTHETIC pages shaped like marianos.com; Chromium
resolves no host except 127.0.0.1, so nothing reaches Mariano's or Scrapfly. The delivery's
`PACKAGE_VERIFICATION.txt` repeats these checks from a clean extraction of the source ZIP.

| Area | What is checked |
|---|---|
| 22-field contract | field order, strings only, `""` for missing, `gupc`/`unit_price` empty, UPC 13 digits as shown, prices and PPM as displayed, volume deals and digital coupons apart, weight-priced products excluded, products shown without a price kept with empty prices; CSV export with the same 22 columns |
| Store selection and checks | the store selected with the site's own picker; every page step checked for store 53100503 and In Store (page details, the picker confirmed in this session, the store of every product request); a store the picker does not list stops the run before any product (exit 7) and holds the store |
| Task lease | a page load or store selection longer than the task's lease keeps the task (the lease is renewed every 30 s while the browser works); a preflight taken over after a lost lease selects and verifies the store again before any collection |
| Entry page | an optional page opened once per browser session before the first listing (`acquisition.entry_url`, off by default) |
| Canary | the first recorded page step's valid records compared with the site's product responses by a separate reader (UPC, the store the price is for, regular and sale price); a disagreement, or fewer than half found, stops the run (`CANARY_CHECK_FAILED`) |
| Paging | "Load More" steps counted only with paging evidence for the configured store; the page-step limit |
| Provider | the key from `SCRAPFLY_API_KEY` or a mounted key file, never stored or logged; the account read before and after each segment; the credit budget and the account reserve stop the run and close the browser; the browser is closed on failure, cancellation and timeout |
| Publication (fault injection, offline) | a refusal, a rejected run and a crash before, during or after the publication's commit leave the published dataset as it was (or repair it from the database) |
| Runs, interruption, schedule, CLI, isolation | as for the Walmart collector (same job logic): limits, finalization, publication of complete runs only; SIGTERM, SIGINT or (Windows) Ctrl+Break close the browser, leave the run `interrupted` (`TERMINATED`) and `resume` finishes it; the schedule ships **disabled**; the store-local schedule guard; exit codes and JSON log lines; no import outside the package and its declared dependencies |

**Authentic captures, offline.** `tests/fixtures/live_2026-10-20` and `tests/captures/run_01M5CSS9_20261020`
(records and product responses of the deployed application's live run `01M5CSS9M30WBFTASHHCAWXKPS`,
2026-10-20) are rebuilt and checked offline. These are earlier captures, not new evidence.

## 2. The HTTP 403 of 2026-10-21: diagnosis

**Confirmed from saved evidence (no credit spent):**
* 2026-10-21, run `01M5FX7RJHA5HNCEQ1ZBNPM68H` of this package: the first listing page was answered with
  HTTP 403 "Access Denied" (an Akamai edge page with a reference number); the collector stopped
  (`SITE_REFUSAL`), closed the browser and held the store; 13 credits.
* 2026-10-20, the deployed application (same browser provider and settings): run `01M5C3S9…` was refused
  the same way on its first listing at 07:35 UTC; run `01M5C3TQ…` one minute later collected 151 products
  and was then refused on a later page; run `01M5C42S…` four minutes later collected 353 products without
  a refusal; the scheduled run at 14:00 collected 139 until the credits ran out. The refusal therefore
  comes and goes between browser sessions minutes apart, with the same code and settings, and can occur
  on the first page or later.
* Scrapfly's Cloud Browser documentation (read 2026-10-22) gives no guidance for target-site refusals;
  its separately billed unblocking and captcha-solving features are not used (challenge solving is out of
  scope).

**Hypothesis tested live (one session):** *H1: this package's own configuration causes the refusal.*
Session 1 on 2026-10-22, with the configuration unchanged, received HTTP 200 for the listing; so did the
two following sessions (19 navigations in the last one). **H1 is not supported.** What remains is a
per-session refusal by the site's bot protection, which this collector cannot influence without rotating
identities or solving challenges, neither of which it does. **No code change was made for the 403**: the
refusal is detected (HTTP 403, the access-denied text and the Akamai reference), the run stops, the
browser closes, the store is held, and an operator decides when to release the hold and try again. The
defects that did block today's runs are listed in section 6. A provider support request is not needed
while sessions succeed (none was written or sent).

## 3. Live checks (workstation, not Azure)

Scrapfly key `…0e5a71` (free plan; read from a local key file, never copied into any file of this
package), store 53100503 Marianos Lakeshore East, 333 E Benton Pl, Chicago, IL 60601, In Store. Each
command ran as its own process through `scripts/headless_live_campaign.py`; balances are Scrapfly's own
account readings. Session 1 was the diagnostic (193 credits, about one minute: within the 300-credit
diagnostic limit); sessions 2 and 3 were the demonstration (483 credits, about 8.5 minutes of browser
time), all from the account's existing free-plan credits.

| Run | Time (UTC) | Code | Result | Scrapfly credits |
|---|---|---|---|---|
| `01M5HWVX3235VMQ0JE6Q4TENVM` | 13:30–13:31 | `59172cd` | session 1 (H1): the listing answered **200** (3.4 MB in 26 s); the run budget set for the test (150) was lower than the projected cost of the next step, so it stopped before the store selection (`RUN_CREDIT_LIMIT`); browser closed; 0 products | 884 → 691 (193) |
| `01M5HXNKCCF5QF6077G8J3N0CC` | 13:44–13:46 | `59172cd` | session 2: pages answered 200 and the store picker ran; the preflight outlived its 120-s task lease, another worker took the task over and found the store not selected; the run ended `NOTHING_TO_COLLECT` with a misleading message; browser closed; 0 products. **Defect, fixed in `9ddd6f7`** | 691 → 545 (146) |
| `01M5HY42M54T71B5JJ5ZCN91NK` | 13:52–13:58 | `9ddd6f7` | session 3: the store selected with the site's picker and verified ("In-Store at Marianos Lakeshore East"), canary passed, Grocery › Crackers read to its end (10 "Load More" steps, 243 of the 253 products the site announced), Packaged Breads started; stopped at the run budget (450, `RUN_CREDIT_LIMIT`, resumable); browser closed; **264 valid products**, 0 excluded | 545 → 208 (337; the collector estimated 399) |

`validate-export --run 01M5HY42…` passed: the manifest and files verified, the 22-field contract passed,
and the independent check found 241 records equal to the site's own product responses for the store, 23
whose page step's responses did not include them (reported, not assumed), none different. The run is a
**pilot** (narrowed on the command line): exported, never published. **Not reached: 500 products** (264;
the 208 credits left are about one more session's store selection and first page).

## 4. Container: NOT RUN (pending)

No Docker is available on the preparation workstation, so the image has not been built or started. The
same CLI was run from the locked environment (`uv sync --frozen`), which is what the image installs; the
image installs no browser (the cloud browser is Scrapfly's).

## 5. Azure: NOT RUN (pending)

No Azure subscription or credentials were available. Option A (Container Apps, `azure/main.bicep`)
compiles and lints without warnings (Bicep CLI 0.48.1); option B (one VM, AZURE_VM.md) is documented
only. Nothing was deployed or provisioned and no Azure charge was incurred.

## 6. Found and fixed while verifying

* 2026-10-22, live: the task's 120-s lease was not renewed while the browser worked, so a slow store
  selection let the task be taken over and the run stop; the lease is now renewed every 30 s, and a
  preflight taken over verifies the store again (`9ddd6f7`, two regression tests that fail on the old code).
* 2026-10-22: Windows had no stop signal the collector listened to (Ctrl+Break added, `59172cd`); the
  schedule shipped enabled (now off, `09f3575`); the browser session's own events were not kept in the
  database (now `SESSION_*` events, `09f3575`).

## 7. Not verified

* A full-scope run (294 listings; estimated at 17 to 18 hours of collection, OPERATIONS.md); the
  twice-weekly cost is an estimate.
* Publication of a live run (pilot runs are never published; publication is tested offline only).
* The entry page option live (it is off; no session used it).
* An authentic in-stock to out-of-stock change in the 2026-10-22 runs (one run only; historical examples
  are in the evidence package).
* The twice-weekly schedule firing in Azure.
