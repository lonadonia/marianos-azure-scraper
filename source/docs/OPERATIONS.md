# Operations

## Setup

### Local (a workstation or a server)

1. Python 3.12 and uv; `uv sync --frozen` installs the exact locked versions (`uv.lock`). No browser is
   installed: Oxylabs loads the pages on its side; Scrapfly's cloud browser is driven over CDP.
2. A PostgreSQL database for this collector alone (never shared with another collector's tables).
3. `cp .env.example .env` and fill in `MARIANOS_COLLECTOR_DATABASE_URL` and the key of the provider named in
   `config/settings.yaml` (Oxylabs: `OXYLABS_WEB_API_KEY_FILE` naming a file readable only by the service
   user, mode 600; Scrapfly: `SCRAPFLY_API_KEY` or `SCRAPFLY_API_KEY_FILE`). `.env` is never committed or
   packaged.
4. `marianos-collector db-upgrade`, then `marianos-collector validate-config --check-db --require-credentials`
   and `marianos-collector provider-balance`. With Oxylabs, set the ceiling first (below).

Data goes to `./data` (or `MARIANOS_COLLECTOR_DATA_DIR`). For a container, the same with the image
(Dockerfile): `docker run --env-file .env marianos-collector:1.8.0rc5 validate-config --check-db` (the tag the
image was built with).

### Azure

See [AZURE.md](AZURE.md): build the image, put the two secrets in Key Vault, deploy `azure/main.bicep`,
run `db-upgrade` through the operations job.

## Operation

* **Scheduled collection.** Each store's Azure job fires every 30 minutes; `run --scheduled` starts a new
  run only at the store-local start time of a scheduled weekday (twice a week by default, Monday and
  Thursday 07:00 America/Chicago). The other firings inside the daily window (07:00 to 19:00, any weekday)
  continue that run while it is unfinished, one execution of at most `max_segment_minutes` (300) at a time;
  the rest exit in seconds. The next occurrence closes a run still unfinished then as partial (never
  published) and starts the new one. AZURE.md (Schedule, continuation and daylight-saving time) has the
  details. The shipped configuration has the schedule **off** (`collections.<store>.schedule.enabled:
  false`) until the client approves it; with it off a firing exits 0 with `SCHEDULE_OFF`.
* **What a run reads.** For each configured category row, the listing pages the saved site menu
  (`config/taxonomy_seed.snapshot_2026-10-17.json`) names for it; on each listing, every page (24 products
  each): with Oxylabs (release 1.8.0) the listing's own page with `?page=N`, with Scrapfly each "Load More"
  step. The run loads robots.txt (and stops if it cannot), sets the store (Oxylabs: the request's `store_id`
  and `fulfillment_type`, verified on every page; Scrapfly: the site's own store picker in a cloud browser
  session), then checks every page against the store before any product counts. The five rows the saved menu has no entry for but whose CSV URL is itself a listing
  page (`/pl/<name>/<taxonomy id>`: Candles Home Fragrances, Batteries, Light Bulbs, School Office,
  Hardware Home Improvement) are read as that listing, with an empty `sub_category`. The Coupons row lists
  offers, not products: it is reported in the run's plan as not collected, with that reason.
* **Manual collection.** `run --store KEY` (with `--categories`, `--subcategory` or limits for a bounded
  pilot). In Azure, through the operations job (AZURE.md, Operations).
* **Stop, resume, finalize.** `stop` asks a running execution to stop at its next checkpoint and finalize.
  `resume` continues an interrupted run from its checkpoints. `finalize` exports what an unfinished run
  collected without opening a browser.
* **Publication.** Only a complete, validated, non-pilot run is published: `published/<store>/latest.json`
  names the run and its manifest; the database pointer is authoritative. A pilot, partial or rejected run
  keeps its exports under `runs/<store>/<run>/exports/` (or `exports-<time>/`), labelled in its manifest
  (`"dataset": "pilot" | "partial"`), and never replaces the published dataset.
* **What a run exports.** `products.json` and `products.csv` (the 22 fields): the store's retained
  dataset, i.e. the products this run observed plus the store's products verified by earlier runs and
  carried forward unchanged with their own crawl dates; `products_fresh.json` and `products_fresh.csv`
  (release 1.2.0 on; since 1.4.0 only this run's own `valid` records, so a clean dataset with no unpriced,
  conflicting or carried record); `memberships.json` (every placement: store, fulfillment, run, collection
  segment, product, CSV row and category, listing, page, position, organic or sponsored, page copy and
  observation time; release 1.4.0), `offers.json` (coupons and deals with their terms), `provenance.json` (the supporting log:
  per product, fresh or carried forward, the stored page copy and its SHA-256, the page step and store
  check that observed it, field sources, why each empty field is empty, exclusions with reasons, the code
  version), `validation_report.json` and `manifest.json` (hashes of every file, record counts).

## Capacity of one run (measured rates; read before enabling the schedule)

This section measures the Scrapfly route (2026-10-23); the Oxylabs route's measured times and costs are in
each delivery's COST_AND_RUNTIME_REPORT. Each page step runs in Scrapfly's cloud browser, one at a time.
Measured on 2026-10-23 (VERIFICATION.md):
selecting the store with the site's picker took about 2.5 minutes per browser session, opening a listing
about 30 s and each "Load more" step 15 to 19 s (about 23 new products per step). A session lasts at most
30 minutes (a new one opens after 18), about five listings each.

**The site's result window.** Every products-search response of 2026-10-23 stated `availableCount` 250:
a listing page lets the visitor reach at most 250 of its results, whatever total it reports (Cereal &
Granola 328, Yogurt 386 at the selected store). Release 1.2.0 marks such a listing INCOMPLETE with the
site's numbers when Load More ends at the window. From release 1.2.1 (`coverage.partition_large_listings`,
on), a listing whose total exceeds the window is read through the child listings the site's own category
facet names for it (in the same products-search response: id, name and count of each child): the
products of its first page are kept, each child listing becomes a listing task of the run, checked against
the store and paged like any listing (and partitioned again if it exceeds the window itself), and each
product is recorded once (by UPC). The listing counts as complete only when its distinct products, with its
children's, reach the total the site reported for it; the children's counts overlap (Cereal & Granola:
240 + 71 + 24 + 14 = 349 for 328 results) and are never added up. Otherwise the listing is INCOMPLETE with
the gap, and the run is not complete. A listing above the window whose facet names no children stays
INCOMPLETE. **Verified offline only (mock site); no live run has used it yet.** A product shown only as
another size or flavour of a card ("3 more sizes") is not a card of the listing and is not collected; the
coverage report counts such cards (a known gap).

The client's rows name **299 listings** (294 from the saved menu and the five row listings). Their sizes
are not measured beyond five (208 to 386 results). At up to 11 page steps per listing (the window), a
full-scope run is roughly 299 × (30 s + 11 × 17 s) ≈ 18 hours of collection plus about 60 store
selections, about **20 hours**; partitioning the larger listings would add to it. That is longer than one
execution (`max_segment_minutes`, 300) and one day's window (07:00 to 19:00), so a run is carried by
several executions (AZURE.md, Schedule, continuation and daylight-saving time): each pauses at its
checkpoint and the next continues it, within `max_run_minutes` (2880) and before the next occurrence
supersedes it. Until it completes it is a partial run and never replaces the published dataset. **No
full-scope run has been executed.**

### Release 1.9.0: lanes and the schedule's real capacity (M8)

`limits.max_concurrent_listings` (default 1, at most 4) lets one execution read that many listing tasks
at once, each with at most one provider request in flight; the run's spending ceiling, limits and
checkpoints are shared, and a lane that stops the run halts the others. A page is written to the database
only once its answer has been processed (1.9.0rc4; in 1.9.0rc3 one lane could write the other's page while its
request was still out, without its stored page, and the integrity check G13 rejected the run: stage S5b,
2026-11-09). Keep one lane unless a two-lane run of the release in use has passed its checks (the delivery's
report lists the live runs). `collection.schedule.capacity`
gives the collection hours an occurrence's run has before the next occurrence supersedes it: with the
shipped Monday/Thursday 07:00 schedule, the 07:00-19:00 window and `max_run_minutes` 2880, a Monday run
has 36 collection hours (72 elapsed) and a Thursday run 48 (96 elapsed), against a full-scope workload
estimated at 48.4 to 77.3 active hours with one lane (an estimate, not a measured full run; the
delivery's COST_AND_RUNTIME_REPORT has the measured rates and the proposed configuration). The schedule
stays off until the client authorizes one.

## Monitoring

* **Exit codes** of each execution (Azure shows them per execution; CLI.md lists them). Anything but 0 needs
  a look; 8 repeats until someone releases the hold.
* **Logs** in Log Analytics (`ContainerAppConsoleLogs_CL`, or `ContainerAppConsoleLogs` in newer
  workspaces). Each line is JSON; for example:

  ```kusto
  ContainerAppConsoleLogs_CL
  | where ContainerJobName_s startswith "marianos"
  | extend e = parse_json(Log_s)
  | where e.event in ("RUN_FINISHED", "COLLECTION_HELD", "UNEXPECTED", "TERMINATED", "PUBLICATION_REFUSED")
  | project TimeGenerated, ContainerJobName_s, e.level, e.event, e.exit_code, e.run_id, e.stop_code, e.message
  ```

  Alert suggestions: any `ERROR` line; `RUN_FINISHED` with `exit_code != 0`; no `RUN_FINISHED` for a store
  in 4 days; the balance from `provider-balance` below the next run's need.
* **`status`** (operations job, or locally): holds, last runs, published dataset, last account reading.
* **Credits.** Scrapfly bills the cloud browser by session time and bandwidth (residential traffic costs
  far more than datacenter). The collector estimates the credits of its session from the published rates
  and stops before the estimate passes the run's budget (`limits.max_credits_per_run`, the day's budget
  and `min_credit_reserve` against the account balance read at the start of each segment;
  `acquisition.scrapfly.max_credits_per_run` caps a browser session only when none of those applies);
  `BROWSER_CLOSED` records the estimate, and the account reading before and after each segment gives what
  was actually charged. `bandwidth_overhead_factor` scales the page meter's bytes to the billed traffic
  (measured 1.7 on 2026-10-20, then 1.3, 1.9 and 1.8 on 2026-10-23; the delivered 2.0 errs on the side of
  stopping early).
* **The provider's browser.** `acquisition.scrapfly`: residential US proxies, the browser platform
  `browser_os` (the provider's `os` parameter; null delivered: `macos` was tested live and the provider's
  browsers still reported Linux and Windows, see [DIAGNOSIS_403.md](DIAGNOSIS_403.md))
  and the session length `session_timeout_s` (1,800 s, the provider's maximum; a new session, with the
  store selected and verified again, opens after 60 % of it). They are chosen before the first request and
  never changed after a refusal.

## Backup

* **Database.** Azure Database for PostgreSQL keeps automated backups with point-in-time restore (7 days by
  default, up to 35: set it on the server). Locally: `pg_dump -Fc` of the collector's database, kept away
  from the machine. The database holds the runs, records and publication pointer.
* **Blob container.** Turn on blob soft delete and versioning on the storage account; the stored pages and
  responses, the exports of every run and `published/` are there. The published dataset can also be copied
  out with `export --store KEY --out DIR`.
* **Configuration.** `config/` is part of the source (and the image); keep it under version control.
* Secrets are not backed up by the collector: Key Vault keeps versions and soft-deleted secrets.

## Maintenance

* **Upgrade.** Build and push the new image, update the jobs' image (`azure/deploy.sh` does both), then
  run `db-upgrade` through the operations job before the next scheduled execution. Schema changes ship as
  migrations in the package; `run` refuses a database whose schema is not current.
* **Configuration changes** (stores, categories, limits, schedule, browser settings) are files in
  `config/`: edit, rebuild the image, update the jobs. `validate-config` before deploying.
* **The site menu.** The listing pages come from the menu saved on 2026-10-17. When the site changes its
  menu, a listing may move: a page without the content it must have stops the run (exit 5 or 6). Save a
  new menu snapshot (same format: `rows[].menu_nodes[]` with `title`, `taxonomy_id`, `url`) and point
  `taxonomy_seed_file` at it.
* **Stored pages.** Each run keeps the page copies, screenshots and site responses it read
  (`runs/<store>/<run>/live/`). Add a Blob lifecycle rule to delete `runs/` blobs older than your retention
  (e.g. 90 days).
* **Dependencies.** `uv lock --upgrade`, run the tests (`uv run pytest`; the browser tests need a local
  Playwright Chromium: `uv run playwright install chromium`), rebuild. Keep the Playwright pin compatible
  with Scrapfly's cloud browser.

## Recovery

| Situation | What happened | What to do |
|---|---|---|
| Exit 75, `TERMINATED` | The job timed out or was stopped; the browser was closed and the run is `interrupted` with its checkpoints | `resume --store KEY` (or let the next scheduled occurrence close it as partial and start anew) |
| Exit 75, `PROVIDER_ERROR` after the automatic resumes | Scrapfly's browser kept failing (connection, session lost) | check Scrapfly's status, then `resume` |
| Exit 3 | No key, Scrapfly refused it, or the account is suspended (the store is held for `PROVIDER_AUTH`) | fix the secret or the account, `release-hold`, `resume` |
| Exit 4 | The account's credits, the reserve or a budget ran out; the partial run is exported, nothing published | wait for the next billing period or raise the budget; the next run starts anew |
| Exit 5, store held | Mariano's refused access (HTTP 403 "Access Denied", a challenge) | nothing is retried with another identity; read the run's events and stored pages, wait, then `release-hold --reason ...` |
| Exit 7, store held | The picker could not select the store, a page was not for the run's store and fulfillment, or the canary records differ from the site's data | read the run's events and stored pages; fix (configuration, code) before `release-hold` |
| Exit 6 | The run's checks rejected it (coverage, yield drop, integrity) | `status --run` lists the failed checks; the published dataset is unchanged |
| Exit 9 | Another execution holds the store, or an unfinished manual run blocks it | wait; or `resume` / `finalize` that run |
| An execution died (node loss) | The run looks active but no execution holds its lock; Scrapfly closes the browser when the connection drops (`auto_close=true`), at the latest at its session timeout (1,800 s) | the next command recovers the run (`RUN_RECOVERED`), `resume` continues it |
| `latest.json` missing or stale | written after the database commit | the database pointer is authoritative; the next publication rewrites it |
| A forced kill (SIGKILL, lost machine) during collection (release 1.4.0) | The segment stayed open; a provider request may have been in flight | the next execution of the store (it holds the store lock) closes the segment as `abandoned`: its end stays unknown, between its last heartbeat and the recovery time (`SEGMENT_ABANDONED` event); an unsettled Oxylabs request is settled `interrupted_unknown` with its reserved cost kept (possibly billed, counted once). The run resumes from its last committed checkpoint. A worker whose segment was closed this way stops at its next heartbeat (`LEASE_LOST`) |
| A published dataset must be withdrawn (release 1.4.0) | — | `rollback-publication --store KEY --reason TEXT`: the pointer goes back to the publication the current one replaced, after that publication's files are verified again; audited; nothing is deleted |

## Adding a store

1. Add an entry to `config/stores.yaml`: key, `location_id` (3-digit division + 5-digit store, e.g.
   `53100503`), `division_number`, `store_number`, the expected name, ZIP and street address as the site
   shows them, `modality: IN_STORE` or `PICKUP`, timezone, `store_page_url`.
2. Add `collections.<key>` to `config/collector.yaml` (categories, limits, schedule, timezone).
3. `marianos-collector validate-config`, then `schedule-info --store <key>` for its UTC cron.
4. Add `{storeKey, cronUtc, jobName}` to the `schedules` parameter of `azure/main.bicep`, rebuild and deploy.

The first run selects the new store with the site's picker and checks it on every page step; if the picker
does not list it, or a page is for another store, the run stops (exit 7) before any record is exported.

## Adding or changing categories

Edit `config/Marianos_Category_URLs.csv` (same columns: `Retailer,Category (Auto),URL,Scope,Notes`). Rows
are numbered from 0 in file order; `collections.<store>.categories` lists the rows to collect (empty =
all), `subcategories` narrows a row to some listings (`{"1": ["06111"]}`). A new row is collected only when
the saved site menu names its listing pages (its row index in `taxonomy_seed.snapshot_2026-10-17.json`);
otherwise the plan lists it as not collected. A row removed from the CSV is disabled in the database at
the next run, never deleted.

## Oxylabs Web API: the spending ceiling

Oxylabs gives no balance or usage reading for a Web API key, so the collector keeps its own ledger
(`provider_usage`): every submission is reserved under a database lock before it is sent and settled after
the answer (a documented free failure, such as `REQUEST_FAILED_AFTER_TOO_MANY_RETRIES`, costs nothing; an
answer lost in transit is kept as possibly charged). Before a run, the operator sets what it may spend:

```bash
marianos-collector set-ceiling --provider oxylabs --submissions 320 --usd 0.48 --reason "authoritative run"
marianos-collector provider-balance      # room_submissions, usd, all_time
```

A run without a ceiling sends nothing (`SPENDING_CEILING`, exit 4). When the ceiling is reached the run stops
resumably at its checkpoint; `set-ceiling` again and `resume`. Set the ceiling to 0 after the last run of a
campaign. The ceiling counts this database's submissions only: another collector or person using the same
Oxylabs account spends from the same account balance, which this ledger cannot see.

## Replacing the Oxylabs key

Write the new key to the protected file named by `OXYLABS_WEB_API_KEY_FILE` (the service user only, mode
600), then `validate-config --require-credentials`: its result shows the key's fingerprint, never the key.

## Replacing the Scrapfly key

* Azure: add a new version of the Key Vault secret `marianos-collector-scrapfly-api-key`. Container Apps
  reads Key Vault references when an execution starts (references are refreshed periodically); run
  `provider-balance` through the operations job and check the fingerprint in its result.
* Locally: change `SCRAPFLY_API_KEY` (or the key file).

The key is never stored in the database: only its fingerprint and the account readings are. Never put
the key in `config/`, the image, or a log.
