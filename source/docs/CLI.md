# marianos-collector: command reference

```
marianos-collector [--config FILE] [--pretty] <command> [options]
```

`--config` defaults to `$MARIANOS_COLLECTOR_CONFIG`, else `config/collector.yaml`. Every command reads the
database from `MARIANOS_COLLECTOR_DATABASE_URL` (except `validate-config` without `--check-db`,
`schedule-info`, `validate-export --file` and `ops` itself) and, when it collects, the key of the configured
provider (Oxylabs: `OXYLABS_WEB_API_KEY` or `OXYLABS_WEB_API_KEY_FILE`; Scrapfly: `SCRAPFLY_API_KEY` or
`SCRAPFLY_API_KEY_FILE`). Every command but `db-upgrade` refuses to work on a database
whose schema is not current (exit 2).

## Output

Standard output carries one JSON object per line (Azure sends it to Log Analytics):

```json
{"ts": "2026-10-21T14:02:11.204Z", "level": "INFO", "event": "PAGE_COLLECTED", "collector": "marianos-azure-headless",
 "run_id": "01M5...", "message": "Produce › Fresh Fruit: page step 0", "data": {"cards": 24, "new_verified": 20, ...}}
```

`level` is `INFO`, `WARN` or `ERROR`; `event` is a stable code (below). The last line of a command is
`{"event": "RESULT", "command": ..., "exit_code": ..., "result": {...}}`; `--pretty` prints the result
indented instead of that line. A key value is never written: keys appear only as a 6-character fingerprint
(`…0e5a71`). `MARIANOS_COLLECTOR_LOG_LEVEL` (`DEBUG`, `INFO`, `WARN`, `ERROR`) filters the lines.

## Exit codes

| Code | Meaning | Typical next step |
|---|---|---|
| 0 | Done: the run validated (or published), a bounded pilot collected what its limits allowed, or there was nothing due | none |
| 1 | Unexpected error (logged as `UNEXPECTED` with its type) | read the log; resume if a run was interrupted |
| 2 | Configuration: invalid file, missing database URL, schema not current, unknown store or run | fix the configuration; `db-upgrade` |
| 3 | Credentials: no key for the configured provider, or the provider refused it (Scrapfly: or reports the account suspended) | set or replace the key (OPERATIONS.md) |
| 4 | Credits: the account's credits, the credit reserve or a credit budget ran out; for Oxylabs, no ceiling is set or the ceiling is reached (`SPENDING_CEILING`, resumable) | add credits, raise the budget or `set-ceiling`; the partial run is kept |
| 5 | Site refusal: Mariano's refused access (HTTP 403/429, an Akamai "Access Denied" or challenge page) | the store is held; investigate, then `release-hold` |
| 6 | Rejected: the run's checks rejected it, or an export did not verify | read `status --run`; nothing was published |
| 7 | Store or source checks failed: the store picker could not select the store, a page was not for the run's store and fulfillment (the client's: 53100502, Pickup), or the canary's records differ from the site's product data | the store is held; investigate, then `release-hold` |
| 8 | Held: the store's collection is held after an earlier stop | `status` shows why; `release-hold` |
| 9 | Busy: another execution holds the store, or an unfinished run must be resumed or finalized first | wait, or `resume` / `finalize` |
| 75 | Interrupted, resumable: a termination signal (job timeout or stop), or a provider failure that persisted | `resume` (or the next scheduled occurrence closes it) |

## Commands

### validate-config [--require-credentials] [--check-db]
Loads `collector.yaml` and the files it names (settings, stores, category CSV, private-label brands) and
prints the stores, categories, limits, schedule (with the UTC cron expression and the next local start),
canary, historical and publication settings, and whether the database URL and the key are set (the key
only as a fingerprint). `--require-credentials` exits 3 without the configured provider's key (another
provider's key does not count); `--check-db` connects and compares the schema revision with the package's
(exit 2 when not current).

### db-upgrade
Creates or upgrades the schema (Alembic migrations shipped in the package), in one transaction.

### sync-config
Loads `stores.yaml` and the category CSV into the database (rows no longer in the CSV are disabled, never
deleted). `run` does this by itself.

### run --store KEY [--scheduled] [--categories ROWS] [limits]
Creates a run of one store and collects it in this execution. Without limits it collects every listing
page of the configured category rows (the listings the saved site menu names for each row; with Oxylabs,
release 1.8.0, each page of a listing, `?page=N`; with Scrapfly, each "Load More" step). Narrowing on the
command line or a limit makes it a **pilot**: exported, never published.

| Option | Limit |
|---|---|
| `--categories 1,7` | CSV rows (counted from 0) instead of the configured ones |
| `--subcategory 1:06111` | one listing of a row (its taxonomy id in the saved site menu); repeatable |
| `--max-products N` | verified products in this run |
| `--max-pages-per-listing N` | page steps per listing (Oxylabs: each listing page; Scrapfly: the first load and each "Load More") |
| `--max-credits N` | credits this run may spend, in the provider's unit (Oxylabs: submissions; Scrapfly: credits estimated from session time and bandwidth) |
| `--max-minutes N` | active collection time |

At the end the run is finalized: a limit, a credit stop or an operator's stop leads to the checks and the
export of what was collected; a transient provider failure is resumed in the same execution up to
`max_auto_resumes` times. A complete validated run is published (`published/<store>/latest.json`). The cloud browser is closed
whenever collection stops.

`--scheduled` is the Azure job's form: it takes the settings from the configuration only, acts only when
this execution is the store's due local occurrence (see AZURE.md), and does nothing twice for an occurrence.
Its log says what it decided: `SCHEDULE_OFF`, `NOT_DUE`, `COLLECTION_HELD`, `OCCURRENCE_DONE`,
`OCCURRENCE_CONTINUED`, `RUN_SUPERSEDED`, `MANUAL_RUN_OPEN`, `STORE_BUSY`, or `RUN_CREATED`.

### resume (--run ID | --store KEY)
Continues an interrupted run from its checkpoints (products already recorded are not counted again). With
Oxylabs (release 1.8.0) a listing continues at its first page not completed, and no completed page is
requested again; with Scrapfly a listing is opened again and its earlier steps repeated up to the checkpoint.
Refused while the store is held.

### stop (--run ID | --store KEY) [--reason TEXT]
Asks for collection to stop. A running execution stops at its next checkpoint and finalizes; for a run
that no execution is collecting, run `finalize`.

### finalize (--run ID | --store KEY)
Checks and exports what an unfinished run collected, without any provider request. The result is a
partial (or pilot) dataset, kept under the run and never published.

### publish --run ID [--accept-warnings REASON]
Publishes a complete validated run (normally automatic). A run with WARN findings needs a reason; a FAIL
can never be published; the published pointer moves only after every export file is verified again.

### rollback-publication --store KEY --reason TEXT
Release 1.4.0. Points the store's published dataset back at the publication the current one replaced: that
publication's manifest and files are verified from storage first, the pointer moves in one transaction with
its version check (a concurrent publication makes it fail cleanly), the audit log records the reason, and
`latest.json` is rewritten. Exit 6 when there is nothing to roll back to or the earlier files fail their
check. Nothing is deleted.

### status [--store KEY] [--run ID] [--limit N]
The configured stores: whether held (and why), the last runs (status, dataset label, stop reason, record
counts, canary, historical observations, whether an execution is collecting it), the published dataset,
and the provider ledger (credits recorded, last balance reading). With `--run`: that run and its export
files.

### export (--run ID | --store KEY) --out DIR
Verifies a run's export files against its manifest and copies them to `DIR` (with `--store`, the store's
published dataset): `products.json`/`.csv` (the retained dataset), `products_fresh.json`/`.csv` (only the
products this run observed; runs exported by 1.2.0 and later; since 1.4.0 only its `valid` records), memberships, offers, the supporting log, the
validation report, the manifest and, when the manifest lists them (release 1.8.0), the coverage files
`coverage_reconciliation.json` and `.csv`, `coverage_by_csv_row.csv` and `listing_pages.csv`. Each file is
verified against the SHA-256 the manifest records before it is copied (the coverage files from 1.8.0rc4).

### validate-export (--file products.json | --run ID)
The 22-field contract of a products file. For a run, also: the manifest and every export file verified
from storage, and every exported record compared with the site's product data the run stored, read
independently of the parser: each product's data for the store (UPC, the store its price is for, regular
and sale price), from two evidence classes: the site's product responses, and (release 1.2.1) the product
data embedded in the stored page copies (`window.__INITIAL_STATE__`, the objects the page rendered its cards
from). A product response is preferred; a difference with either source is a mismatch, never averaged away.
Each result names its class (`evidence`: `product_response` or `embedded_page_data`), and the summary counts
them (`by_evidence`) with `responses_read`, `pages_read` and `products_in_sources`. A record carried forward
from an earlier run is compared with that run's sources (its prices are from that day).
`products_fresh.json`, when the manifest lists it, must pass the contract and be exactly the retained file's
records of status `valid` observed by this run (release 1.4.0; before it, the retained file without the
carried-forward records). A record found in neither source is reported `unverified`, not a
failure. No provider request. Exit 6 on any other problem (a mismatch included).

### provider-balance
For `scrapfly`: reads the account's balance from Scrapfly's Account API (free; no browser is opened) and
records it (without the key); exit 3 for a refused key or a suspended account, 4 when the credits are used
up. For `oxylabs` (no balance API): the operator's ceiling and the ledger of submissions since it was set
(`room_submissions`, `usd`, `unknown` costs, `all_time`); no request is sent; exit 4 when there is no
ceiling or no room left.

### set-ceiling --provider oxylabs --submissions N --usd X --reason TEXT
The spending ceiling of the Oxylabs Web API for the runs that follow, counted from now: at most N
submissions and X US dollars at the configured rate (`acquisition.oxylabs.usd_per_result`). It replaces the
previous ceiling; both are kept in the audit log with the reason. Every submission is reserved in the
`provider_usage` table under a database lock before it is sent; one that would pass the ceiling is not sent
and the run stops resumably (`SPENDING_CEILING`, exit 4). A run without a ceiling sends nothing.

### release-hold --store KEY --reason TEXT
Lets a held store collect again (recorded with the reason and the previous hold).

### reprocess --store KEY --source-run ID --upcs-file FILE --reason TEXT [--dry-run]
Release 1.5.0. Rebuilds the products listed in FILE (one UPC per line) from what run ID stored (each card as
displayed, its page and the site's product data captured with it) with the current rules, into a new run
(trigger `reprocess`, finished `rejected`: never published). Nothing is requested from the site. Every stored
input is checked against the SHA-256 recorded when it was stored, and the product data must be the response
the original record was built from; any failure refuses the whole request and writes nothing. Each rebuilt
record keeps the original observation time, crawl date and page, is flagged `REPROCESSED`, and carries the
original record (status, reasons, SHA-256), the fields that changed and the reason
(`provenance._reprocessed`). The source run is not modified. A later run that does not observe the product
carries the rebuilt record forward as `historical`, never as fresh. `--dry-run` reports the result and writes
nothing. Refused while the store has an unfinished run (exit 9).

### schedule-info --store KEY
The store's schedule and the UTC cron expressions for its Azure job: `cron_utc` (the local start, for
standard and daylight time) and, when `continue_unfinished` is on, `cron_utc_with_continuation`
(`*/30 * * * *`, the expression to deploy: AZURE.md, Schedule, continuation and daylight-saving time).
When the next occurrence closes an unfinished scheduled run (`SUPERSEDED`, never published), its new run reads
first the listings no run has read to their end, then the others, the one read longest ago first
(`schedule.backlog_first`, release 1.5.0; the order and the backlog are in the run's `plan.order`).

### ops
Runs the command written in `MARIANOS_COLLECTOR_COMMAND` (default `status`), e.g.
`MARIANOS_COLLECTOR_COMMAND="resume --store marianos-53100502-pickup"`. This is the entry point of the Azure
operations job (AZURE.md, Operations).

## Events

Collection: `RUN_CREATED`, `RUN_EXECUTING`, `BROWSER_STARTED`, `BROWSER_OPENED`, `ROBOTS_FETCHED`,
`PAGE_CAPTURED`, `ACTION_CAPTURED` (store picker steps), `STORE_VERIFIED`, `PAGE_COLLECTED`,
`LISTING_PARTITIONED` (a listing read through its child listings), `CANARY_PASSED` /
`CANARY_FAILED`, `CHALLENGE_DETECTED`, `RUN_LIMIT_REACHED`, `RUN_STOPPED`, `BROWSER_RECONNECT`,
`PROVIDER_BUDGET_REACHED`, `BROWSER_CLOSED`, `COLLECTION_CLOSED`. Results: `RECORDS_ASSEMBLED`, `CHECKS_COMPLETE`, `EXPORTS_STAGED`,
`PARTIAL_EXPORT`, `RUN_VALIDATED` / `RUN_REJECTED`, `RUN_PUBLISHED` / `PUBLICATION_REFUSED`,
`RUN_FINISHED` (with the exit code and the run's summary). Control: `SIGNAL_RECEIVED`, `RUN_INTERRUPTED`,
`TERMINATED`, `RUN_AUTO_RESUMED`, `RUN_RECOVERED`, `COLLECTION_HELD`, `HOLD_RELEASED`, `STORE_BUSY`,
`COMMAND_REFUSED`, `CONFIG_INVALID`, `UNEXPECTED`. Also logged: `RUN_<STATE>` on each change of the run's
state (`RUN_PREFLIGHT`, `RUN_RUNNING`, `RUN_VALIDATING`, ...), `SEGMENT_STARTED`, `PROVIDER_SESSION_OPENED` /
`PROVIDER_SESSION_CLOSED`, `COUPONS_ROUTE`, `PAGE_NOT_COUNTED` (release 1.8.0: a listing page recorded with its
verdict and not counted), `NODE_DONE`, `TASK_RETRY`, `TASK_LEASE_RECLAIMED`, and inside a provider session the
same events prefixed `SESSION_` (`SESSION_PAGE_CAPTURED`, `SESSION_ROBOTS_FETCHED`, ...).
