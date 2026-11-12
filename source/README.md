# marianos-azure-headless

A headless collector of Mariano's store prices for one or more configured stores, built to run as Azure
Container Apps Jobs or on a Linux VM. Each run collects with **one** page provider, named in
`config/settings.yaml` (`acquisition.browser_provider`) and recorded with the run; a run never switches
provider:

- **`oxylabs`** (release 1.3.0, the shipped default): the Oxylabs Web API's Mariano's scraper. The store
  and fulfillment are request parameters (`store_id`, `fulfillment_type`); every page is checked against
  them (the page's own store, modality and search request, and the store each product's prices are for).
  From release 1.8.0 a listing is read page by page: its own `/pl/` page by URL with `?page=N`
  (`acquisition.oxylabs.listing_route: listing`, the default); from release 1.9.0rc2 without rendering
  (`listing_run_js: false`; since 2026-11-06 the unrendered page carries the product tiles, a rendered one
  none). Oxylabs has no balance API: an operator ceiling (`set-ceiling`) limits the submissions, each
  reserved in the database before it is sent.
- **`scrapfly`**: Scrapfly's Cloud Browser (a Chromium run by Scrapfly, reached over the Chrome DevTools
  Protocol), which selects the store with the site's own store picker. The retailer's edge refused it on
  2026-10-28 (HTTP 403, then 429); it stays available, unchanged.

Every page is checked against the configured store and fulfillment, and the products are exported with
exactly the client's 22 fields. There is no web interface and no login. The Kroger Public API was tested as
a third source (`probes/kroger_api.py`); it is not a collection mode (PROVIDER_COMPARISON in the delivery).

Configured store (release 1.8.0): **Marianos Vernon Hills**, location 53100502, 1720 N Milwaukee Ave,
Vernon Hills, IL 60061, **Pickup** (`config/stores.yaml`, key `marianos-53100502-pickup`). Marianos Lakeshore
East (53100503, In Store, key `marianos-53100503-instore`), the store of the releases before 1.8.0, stays in
the configuration as development evidence only.

Derived from the deployed application (mscraper 1.2.6, commit `f9c03085`): the Mariano's collector, its
cloud-browser session, store selection and store checks, the site parsers, record rules, validation checks
and export format are that application's, moved into a standalone package (`marianos_headless`) with its
own command line, database schema and configuration. Nothing here needs the original application, its
database or its files.

## What runs where

| Where | What |
|---|---|
| Azure Container Apps Jobs | `marianos-collector` (this package): one scheduled job per store, one manual operations job. Each execution runs one command and exits. No browser runs in Azure. |
| Azure Database for PostgreSQL | runs, task checkpoints, records, store locks, holds, publications (one database for this collector). |
| Azure Blob Storage | the stored pages and site responses of each run, its exports, and `published/<store>/latest.json` (one container for this collector). |
| Azure Key Vault | the provider key and the database URL, read by the jobs through their managed identity (on a VM: a protected environment file, mode 600). |
| Oxylabs Web API | loads the Mariano's search page for the requested store and fulfillment (`webapi.oxylabs.io`, Bearer key) and returns it with the page's product data; no browser runs on the collector's side. |
| Scrapfly | runs the cloud browser (residential proxy, US) that loads marianos.com; the job drives it over CDP (`wss://browser.scrapfly.io`) and closes it when it stops. Scrapfly's Account API (free) reports the credit balance. |
| Mariano's | serves the pages and their product data to the provider. |

## Quick start (local)

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/), a PostgreSQL database, the key of the
configured provider (Oxylabs: `OXYLABS_WEB_API_KEY_FILE` naming a protected file).

```bash
uv sync --frozen
cp .env.example .env            # fill in MARIANOS_COLLECTOR_DATABASE_URL and the key file (never commit .env)
set -a; . ./.env; set +a
uv run marianos-collector db-upgrade
uv run marianos-collector validate-config --check-db --require-credentials
# Oxylabs has no balance API: set the spending ceiling for the next runs (counted from now), then read it
uv run marianos-collector set-ceiling --provider oxylabs --submissions 40 --usd 0.06 --reason "first pilot"
uv run marianos-collector provider-balance       # the ceiling and the ledger (Scrapfly: the account's credits)
# A small, bounded run (labelled "pilot", never published): CSV row 23 (Candles), one page per listing, at
# most 10 products and 10 submissions (Oxylabs credits are submissions; robots.txt and the Coupons page count)
uv run marianos-collector run --store marianos-53100502-pickup --categories 23 \
    --max-pages-per-listing 1 --max-products 10 --max-credits 10
uv run marianos-collector status --store marianos-53100502-pickup
```

The exports of a run are under `data/runs/<store>/<run>/exports/` (`products.json` and `products.csv`:
the store's retained dataset; `products_fresh.json` and `products_fresh.csv`: only what this run observed;
`manifest.json`, the supporting log `provenance.json`, the coverage files of release 1.8.0, ...). A complete
validated run is also published:
`data/published/<store>/latest.json` names it.

## Commands

`validate-config`, `db-upgrade`, `sync-config`, `run` (`--scheduled` for Azure), `resume`, `stop`,
`finalize`, `publish`, `status`, `export`, `validate-export`, `provider-balance`, `set-ceiling`,
`release-hold`, `schedule-info`, `ops`. Every command writes JSON log lines and exits with a code that says how it ended
(0 done, 2 configuration, 3 credentials, 4 credits, 5 site refusal, 6 rejected, 7 store or source checks,
8 held, 9 busy, 75 interrupted and resumable). See [docs/CLI.md](docs/CLI.md).

## Documentation

* [docs/CLI.md](docs/CLI.md): every command, its options, exit codes and log format.
* [docs/OPERATIONS.md](docs/OPERATIONS.md): setup, operation, monitoring, backup, maintenance, recovery,
  adding stores and categories, replacing the Scrapfly key.
* [docs/AZURE.md](docs/AZURE.md): the Azure resources, deployment, secrets and managed identity, the
  twice-weekly schedule and daylight-saving time, overlap, timeouts and retries.
* [docs/AZURE_VM.md](docs/AZURE_VM.md): the smallest test on one Linux VM (size checked against measured
  use, permissions without subscription-wide Owner, runtime limits, deallocation and cleanup).
* [docs/VERIFICATION.md](docs/VERIFICATION.md): what was checked, and how (offline, synthetic, live,
  Azure), with the results, for the releases up to 1.2.1; the verification of each later release is in that
  release's delivery (TECHNICAL_REPORT).

## Release 1.10.0 (candidate 1.10.0rc3, not a final release): a request set aside and asked again (C1)

On 2026-11-09 some answers to a listing's page N listed page 1's products, and some first pages of a
listing above the site's 250-result window named no child listing and no brand to subdivide it by; minutes
later the same address was answered properly. Why is not established. With
`limits.max_reasks_per_request` above 0 (shipped: 2 for `marianos-53100502-pickup`; empty or 0 elsewhere,
as in every earlier release) such a request is set aside: its listing waits, the run's other listings are
read first, and the very same request (address, page, listing, filter, store, fulfillment) is asked again
once `limits.reask_min_wait_seconds` (300, the least allowed) have passed since its previous answer or
attempt, at most twice in the run.

* An answer is judged by its products' identities and its verified store, never by its page number, ranks,
  search ID or request ID. A repeat counts no product. When the re-asks are spent the listing is incomplete
  with the reason it had before, and nothing says the listing was read to its end.
* The ceiling is kept in the database (table `deferred_requests`, migration 0006): the count is raised and
  committed before a re-ask is sent, so it holds across listing lanes, restarts and a worker killed while
  the request is out; a re-ask is sent once (the transport's own retries do not apply to it); each one is
  reserved in the spending ledger and checked against every limit like any other submission.
* A first page asked again for its filters counts no product of its own (page state `reasked`): the
  subdivisions it names are read and checked against their own filter as before.
* Every answer is kept, the first one included: what was asked, what the answer states, its stored page's
  hash, the provider's request ID, the distinct products before and after, the overlap, the verdict and
  what followed. A run that set a request aside exports them as `deferred_requests.json`.

Tested offline only (a mock transport and a fake clock; saved answers of 2026-11-09 replayed where they
exist): no live run has used it.

**A refused publication is not a success (1.10.0rc2).** When a complete validated run's automatic
publication is refused (an export that no longer matches its manifest, a WARN finding without a recorded
reason, a lineage problem), the refusal is recorded on the run and logged at ERROR (`PUBLICATION_REFUSED`),
the run's summary says so (`publication`), and the execution ends with exit code 6; a later firing of the
same occurrence ends with 6 again. Releases to 1.10.0rc1 logged it at WARN and ended with 0. The last
published dataset stayed published in every release.

## Release 1.9.0 (candidate 1.9.0rc4, not a final release)

What 1.9.0 changes, each with its regression tests (the delivery's review documents give the evidence):

* **Brand readings and filters (M1, M2).** A brand reading of a listing above the site's result window has an
  ID that is a digest of its full identity (retailer, store, fulfillment, listing, filter, exact brand value;
  migration 0005): 1.8.0rc5 cut it at 64 characters, so two brands sharing their first 58 characters got one
  ID and the second was dropped. A page counts for a brand reading only when it states that very filter, no
  other facet, is the page's latest search and finished loading (verdicts `wrong_filter`, `unbound`). A
  reading planned before 1.9.0 is refused on resume.
* **The product tile served since 2026-11-06 (1.9.0rc2).** Listing pages show `horizontal-product-card-N`
  tiles, search pages `default-product-card-N`; neither shows a size, and no tile was seen showing a coupon.
  The tile is read with its own selectors (earlier saved pages read as before). The weight is the product's
  own customer-facing size in the same page's data (`SIZE_FROM_PRODUCT_DATA`, with its source); a size that
  states no quantity ("N/A", "Count") is not a pack size. A price is read only in the forms seen on the tile
  (a plain price, "Sale: $X discounted from $Y", "about $X each"); any other form exports no price and the
  record is not valid (`PRICE_DISPLAY_UNRECOGNIZED`); a price-per-measure element holding anything else is
  not exported (`PPM_TEXT_UNRECOGNIZED`).
* **Listing pages without rendering (1.9.0rc2).** On 2026-11-06 every unrendered listing answer carried all
  its tiles and every rendered one none (stages S1 and O2), so `acquisition.oxylabs.listing_run_js` is
  `false`. A rendered answer without tiles is not counted and its page is asked for again; three in a row stop
  the run resumably (`PROVIDER_ERROR`). A rendered answer that carries its tiles counts like any other (seen
  on 2026-11-09).
* **Coupon terms from the product's own page (M4).** With `coverage.read_product_terms` on, a product's page is
  read (rendered, once per product and run, never retried, within `limits.max_product_term_reads` /
  `--max-term-reads`) for each coupon's ID, complete terms, displayed expiry, clipping instruction and
  qualifying products; a coupon attaches only to the product whose page shows it. Savings wording ("Save
  $10.00 on 2") leaves `digital_deals_price` empty. A card's coupon whose terms were not read keeps its
  headline, flagged `DIGITAL_TERMS_UNREAD`; a rendered page that disagrees with the card is flagged
  `DIGITAL_TERMS_CONFLICT`. **Tiles (1.9.0rc3):** a tile showed no coupon even for a product whose own page
  shows two (Purina ONE, stages O1 and O2), so an empty coupon on a tile is not an absence: unless the
  product's page was read rendered, the digital fields' reason says the coupon is unknown (missing kind
  `not_attempted`, flag `DIGITAL_COUPONS_UNOBSERVED`), and with the read on every tile's product is a
  candidate. The provider's answers state `run_js` true for 3 of 14 product pages requested with rendering
  (stage O1: one of the three shows coupons, two show no Savings section; corrected in 1.10.0, this said 1
  of 14), so
  this read is costly and mostly inconclusive: off by default, bounded when on.
* **Displayed price per measure (M3).** Never computed; a displayed value that equals the item price on a
  multi-unit pack (`PPM_EQUALS_ITEM_PRICE`) or whose unit family disagrees with the product's own pack data
  (`PPM_UNIT_FAMILY_MISMATCH`) is exported as displayed and flagged as a source-value anomaly.
* **Listing lanes (M8).** `limits.max_concurrent_listings` (1 to 4, default 1) runs that many listing tasks at
  once, each with at most one provider request in flight; preflight, assembly and validation run alone; a
  lane that stops the run halts the others. A page is written to the database only once its answer has
  been processed (1.9.0rc4: in 1.9.0rc3 one lane could write the other's page while its request was still
  out, without its stored page, and G13 rejected the run; stage S5b, 2026-11-09).
  `collection.schedule.capacity` computes the collection hours an
  occurrence's run has before the next occurrence supersedes it (daylight-saving aware).
* **Pause events (T07) and segment ends (T06).** A resumable stop's event names its cause:
  `RUN_LIMIT_REACHED` only for a limit, `RUN_PAUSE_REQUESTED` for an operator, `RUN_PAUSED_ON_FAILURE` for a
  provider failure. The provider session closes and the collection segment ends before records are assembled
  and exported, so the supporting log states each segment's end; a killed segment keeps an unknown end with
  its bounds only (`last_seen_at`, `ended_not_after`), never an invented time.
* **Account-wide spending gate.** An operator's harness can attach `OxylabsClient.account_gate_factory`:
  every submission is then reserved at its worst case in an account-wide ledger before it leaves, settled
  with the provider's request id, and held as unknown when sent without an answer; a refusal sends nothing.

## Collection rules (release 1.8.0, with 1.9.0 above)

* Exactly the 22 fields, in order, all strings, `""` when missing; `gupc` and `unit_price` always empty.
* `upc` as the site shows it (13 digits, leading zeros kept); product URLs and pictures as the site gives
  them.
* Prices as displayed (`regular_price`, `sale_price` with its struck-through price); `ppm` exactly as
  displayed, never calculated; volume deals ("2 For $5.00") and digital coupons kept apart; no calculated
  promotion price.
* Approximate-weight products are excluded on the wording of their weight ("approx. 2 lb", "about 2 lb",
  "avg. 0.75 lb", "~1 lb", "10-14 lb"); a marketing "about" is not a weight. The weight is read where the site
  states it (release 1.5.0, `records.approx_weight_sources`): the displayed weight, then the size in the
  site's own product data (a whole turkey: "10-14 lb"), then, only for a product sold by weight that shows
  no weight, a weight range in its name; each exclusion keeps the wording, its source and the rule. A
  product sold by weight ("about $1.64 each", "$2.39/lb") is kept (release 1.4.0; 1.3.5 and earlier excluded it): its
  displayed price per pound is the `ppm`, its estimated item price is never exported as a fixed price (it
  stays in the supporting log) and no weight is invented. Sizes and packs are kept as separate products
  (one UPC each); a pack label ("Family Pack") is a size fact, not a volume deal.
* Each record has a disposition (release 1.4.0): `valid` (a verified product with a fixed displayed price
  that agrees with its own data for the store), `eligible_unpriced` (a verified product of the store with no
  fixed current price: "Prices May Vary", unavailable, or only an estimated item price; exported with empty
  prices and its availability as the product's own data states it, `unknown` without a stock level),
  `price_conflict` (the displayed price differs from the product's own data: both kept in the supporting
  log, the displayed one exported, never adjusted), `exported_not_valid` (incomplete identity), `excluded`
  (with its reasons). `products_fresh.json` holds only this run's `valid` records; `products.json` the
  retained dataset (every exported disposition and the products carried forward from earlier runs, which
  are never dropped for age). A sponsored card is a product of the listing only when the site's own product
  data places it there (release 1.5.0); the label neither excludes it nor makes it a promotion. Every
  placement, sponsored ones included, is kept in `memberships.json` once per product, listing and placement
  kind, with its page, collection segment and time.
* Records an earlier release's withdrawn rule decided wrongly are rebuilt only by `reprocess` (release 1.5.0,
  docs/CLI.md): from the stored inputs, checked against their recorded SHA-256, into a separate run, with the
  original observation time and crawl date and an audit trail; never as fresh.
* An offer restricted to Pickup or Delivery is left out of an In Store record's deal fields; it stays in
  `offers.json` and the supporting log with the reason.
* Every page is checked against the run's store and fulfillment (the client's: 53100502, Pickup): the
  page's own store details and fulfillment and, by provider, the store picker confirmed in the session
  (Scrapfly) or the request's store and fulfillment, the page's search request and the store each displayed
  price is for (Oxylabs). A refusal, a challenge or a page for another store stops the run and holds the
  store until an operator releases it (a challenge is never clicked through); an abnormal drop in a
  category's yield against the last complete run rejects the run.
* Listing pages (release 1.8.0, Oxylabs route): each response is judged before any of its products count
  (store and fulfillment, page number, listing, repeats and reorders of the listing's earlier pages by
  product identity, empty, malformed, refused or failed). A page that is not accepted is recorded with its
  verdict (`listing_pages`), never counted, and its listing never advances past it; a resume continues at the
  first page not completed. An empty or malformed page leaves its listing incomplete (three in a row stop the
  run, not resumable); a page the provider did not bring leaves it unfinished (three in a row stop the run,
  resumable). A listing is complete only when its distinct products reach the highest total the site
  reported for it; one larger than the site's result window is read through the child listings its own page
  names, and a leaf above the window stays incomplete ("accessible pages exhausted; coverage incomplete").
* Coverage (release 1.8.0): every export reconciles coverage per listing, per CSV row and per page
  (`coverage_reconciliation.json` and `.csv`, `coverage_by_csv_row.csv`, `listing_pages.csv`) with the
  export's identity sets (fresh valid, fresh not valid, carried forward, excluded, duplicates, retained);
  the rows outside the run's scope are listed as NOT_ATTEMPTED.
* A displayed price that the product's own data states for no store is never valid (release 1.8.0,
  `PRICE_STORE_NOT_STATED`): the record keeps the displayed price and is `exported_not_valid`.
* Publication refuses records of mixed lineage (release 1.8.0): fixture records, another store's or a
  fixture run's carried records, records observed on another run's page or with no observation of the run.
* A partial, failed or bounded run never replaces the last complete published dataset.
* Integrity (G13; release 1.8.0rc5): every page the run stored must match its recorded SHA-256, and every
  record its own hash. A request the provider answered with no page stored nothing: it fails the check only
  when a product, offer, placement or listing page of the run names it as a source (1.8.0rc4 rejected a run
  for two such requests).
