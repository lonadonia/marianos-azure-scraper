# oxylabs-classic-probe 1.7.3

An **offline** probe and request plan for the Oxylabs **Classic** Web Scraper API (Realtime method). It holds three things:

- the documented request contract;
- the checks a Classic response must pass before anything more is sent;
- one durable ledger that enforces the proposed campaign limits for both retailers together.

**Its live mode is disabled.** No command of this build sends a request to Oxylabs or to a retailer, and no command reads a credential.

Version 1.7.3 corrects the offline replay's handling of its input (T05). Up to 1.7.2, `replay` created its output folder and an offline ledger before it read the saved responses, and an input it could not use ended in a traceback: a missing `replay.json` or a missing `body_file` in a `FileNotFoundError` (exit 1), `{}` in a `KeyError` (exit 1); a file that was not JSON was refused (exit 2) but only after the folder and the ledger had been created. Now every input is checked first: a missing fixtures folder or `replay.json`, a file that cannot be read, is not UTF-8 or is not JSON, a structure other than `{"steps": {step: [response, ...]}}`, an `http_status` that is not an integer from 100 to 599, a `body` that is not text, a response with both `body` and `body_file`, and a `body_file` that is missing, unreadable or outside the fixtures folder are each refused with one line naming the problem (`{"refused": "ReplayRefused: ..."}`, exit 2), and nothing is created; missing `--targets` or `--rates` files likewise. A valid replay behaves as before. The 23 tests of `tests/test_t05_replay_input.py` were first run on the frozen 1.7.2 code: 22 fail by their output (tracebacks, exit 1, an output folder created) and the control test of a valid replay passes; on 1.7.3 all 23 pass. Nothing else changed: the steps, the response checks, the payloads, the limits and the live refusal are those of 1.7.2.

Version 1.7.2 corrects what the client's review of 1.7.1 reproduced: two gaps in C4, two in C2 and one test that failed on Linux. Each was first reproduced as a test that fails on the frozen 1.7.1 code by its output, on Windows and on Linux (`tests/test_review_of_171.py`, and the drip and hung-worker tests of `tests/test_isolated_transport.py`); 1.7.2 makes each pass. A test named `..._control_...` passes on both and pins what the correction keeps.

- **C4, a body shorter than declared.** A server that declares `Content-Length: 100`, writes `{}` and closes gave 1.7.1 a whole answer (ok, not truncated, renamed to its final `.body`), on a success status or an error status alike, and the campaign parsed it: `http.client` reports such an end as an empty read, not as an error. Now the worker compares what arrived with what was declared. A body shorter than its declared length (including one of which no byte arrived) and a chunked body cut short are kept as `dispatch_NNN.partial` with their status (`IncompleteBody`, the declared and received lengths, the SHA-256), recorded once in the ledger as `PARTIAL_RESPONSE`, never parsed, and their reservation stays held. The transport and the recovery check the declared length again, so a status written by an earlier build cannot pass a short body as whole. A body of exactly its declared length, a response without a body (204, 304, `Content-Length: 0`) and a body of exactly the byte limit stay whole; a body above the limit is still cut at the limit, marked truncated and never decoded. A crash followed by an immediate restart in the same folder keeps the partial, its hash and its accounting, with no paid refetch.
- **C4, a worker killed after it named its file.** When a worker was killed after it had renamed its file (a whole answer to `.body`, or the part that came to `.partial`), 1.7.1 looked only for the worker's unrenamed `.part` file: it reported a whole answer as lost and a kept partial as absent. Now the transport reads the worker's own status first: a whole answer stays the answer, a partial is described with its length and hash, and a status the worker wrote is never overwritten.
- **C4, whose answer it is.** Each worker status now names its dispatch (campaign, ledger genesis id, sequence number, step, attempt and the payload's SHA-256). A recovery keeps a raw answer or a partial only when its status names the ledger row it is recovered into. A status of another dispatch, or one without that identity (written before 1.7.2), is refused, listed with the reason and left on disk as found.
- **C2, one deadline for the whole session.** On Linux the 1.7.1 supervisor waited 1.10 s for a FIFO put at the evidence path despite a hard end of 0.30 s, and it took the complete evidence a previous run had left in the same folder when a new command exited 0 without writing any. Now evidence is read only from a regular file, in bounded chunks and within the time left: a FIFO, a link, a folder or a file above 16 MiB is refused at once, without waiting for a writer. Each session is given an execution id (`CLASSIC_PROBE_EXECUTION_ID`) that its manifest must name, with this campaign and this ledger, and be marked complete; anything else is not this session's evidence. The session's command runs as a process tree (a process group on Linux and macOS, a job object on Windows) that is ended whole whenever the session ends, by itself or not, so nothing it started can dispatch after the supervisor returns. The recovery's bound is handed to its process as a monotonic time, so a wall-clock jump cannot extend it. The supervisor returns within its hard end plus 0.5 s (`supervisor.TOLERANCE_S`), and a charge whose outcome is unknown keeps its reservation.
- **The Linux test.** The client's Linux run of 1.7.1 gave 169 passed, 1 failed and 3 skipped, where Windows gave 171 passed and 2 skipped. The failing drip test expected a forced kill even when the worker stopped by itself at its own deadline, which it does first on Linux. The test now asserts the deadline, the outcome, the partial that was kept and the worker's end, whichever ended it; a separate test makes a worker hang past its deadline and checks a real kill and reap.

C1's redirect and credential protections, C3's checks under the ledger lock and just before dispatch, C5's bounded backoff and the shared accounting are unchanged. The steps, the response checks, the payloads and the campaign limits are those of 1.7.1, live mode stays disabled, and the Mariano's adapter is byte-for-byte unchanged.

Version 1.7.1 completes two findings of the client's review that 1.7.0 described as corrected but had corrected only in part (C2 and C4). Each gap was first reproduced as a test that fails on 1.7.0 (`tests/test_c2_c4_reproduction.py`: 7 tests, all 7 failing on 1.7.0, all 7 passing on 1.7.1):

- **C2, the deadline through recovery, export and cleanup.** In 1.7.0 a supervisor's recovery ran after the session's end with no bound of its own (a ledger lock held elsewhere kept it waiting 30 s, then it raised), the ledger writes after an answer waited up to 30 s for the lock whatever time was left, and a killed session that could not be reaped raised out of the supervisor with nothing recovered. Now the ledger writes after an answer (its index, its settlement, a retry's record, a stop) wait no longer than the session's write window, which ends 30 s before the session's end, and after one refusal of the lock the session does not wait for it again. The supervisor's kill, reap and recovery all end by the session's hard end: the recovery runs in its own process, its waits for the lock end by the same end, and a recovery still running then is killed. What a recovery could not do is listed (`completed`: false, and why). A row it could not mark keeps its money held for the next recovery; nothing is assumed.
- **C4, evidence across crashes.** In 1.7.0 the transport deleted the worker's synced file as soon as it had read it, before the kept copy was written, so a crash between the two lost a paid answer; the evidence manifest was renamed into place without being synced; and a body cut at its deadline left no record. Now each answer is kept as received, privately, under its dispatch's number (`private/raw/dispatch_NNN.body` with its `.status.json`; never exported), synced and renamed durably (a write-through rename on Windows, a synced directory on Linux and macOS). A crash before the kept copy loses nothing: the recovery keeps the copy from those files, once the body matches the hash in its status, without a paid refetch. A body cut short is kept (`dispatch_NNN.partial`) and recorded once in the ledger (`PARTIAL_RESPONSE`, with its length and SHA-256), never as an answer. The evidence manifest is synced before it is renamed into place.

In 1.7.1 the steps, the response checks, the payloads and the campaign limits were those of 1.7.0.

Version 1.7.0 corrected the five findings of the client's second review (C1 to C5) in the shared layer, C2 and C4 only in part (above): no redirect is followed and the credentials go only to the documented endpoint (C1); each exchange runs in its own worker process, killed and reaped at its deadline, with every body, header block and decompression bounded (C2); the ledger reads the clock under its write lock and checks the time and every stop again just before sending (C3); each answer is written to disk and indexed before the next paid step (C4); a backoff is a real wait, bounded by the deadline, and `Retry-After` is honoured up to 60 s (C5). The steps, the response checks and the limits are those of 1.6.0, and the Mariano's adapter is byte-for-byte unchanged.

Version 1.6.0 added the **Mariano's** steps (Mariano's Vernon Hills, store 53100502, 1720 N Milwaukee Ave, Vernon Hills, IL 60061, Pickup) to the Walmart steps of 1.5.2. The Walmart steps, the response checks of the Walmart steps and the campaign limits are unchanged: both retailers run on the one shared ledger, with the same limits as the separately versioned Walmart probe 1.5.2 that ships in the Walmart package. That Walmart package is not modified by this release.

This package is separate from both collectors. It does not use their Oxylabs Web API, Scrape.do or Scrapfly accounts, and nothing here is evidence of what Classic returns.

| What | Status in this build |
| --- | --- |
| Request contract (payload forms, parameter names) | Built from the official documentation: Walmart read on 2026-10-31, Mariano's read on 2026-11-02 ([docs/DOCUMENTED_CONTRACT.md](docs/DOCUMENTED_CONTRACT.md)) |
| Response checks: Walmart (store, fulfillment, identity, pagination, challenge, parser status) | **SYNTHETIC TEST**: tested against invented responses shaped like the documented envelope |
| Response checks: Mariano's (selected store and modality, the search's own store and modality, each price's store, identity, refusal) | **OFFLINE REPLAY**: tested on two real Mariano's pages (Vernon Hills, Pickup) that the Mariano's collector saved through the Oxylabs **Web API** on 2026-11-02, each wrapped in an invented Classic envelope. The pages are real; the Classic envelope is not |
| Shared ledger (10 per retailer, 20 total, 30 minutes, USD 5, headroom, deadline) | **SYNTHETIC TEST**: tested offline, including concurrent processes, crashes and both retailers on one ledger |
| The deadline through recovery, export and cleanup; answers kept across crashes (C2, C4; 1.7.1) | **SYNTHETIC TEST**: tested offline with separate processes, a ledger lock held by another connection, killed sessions and a stub on 127.0.0.1. Not run against Oxylabs |
| Bodies shorter than declared, a worker killed after it named its file, whose answer a raw file is; the evidence path, this execution's own evidence, the session's process tree (C4, C2; 1.7.2) | **SYNTHETIC TEST**: tested offline on Windows and on Linux with a stub on 127.0.0.1 that cuts its bodies short, workers made to hang, a FIFO at the evidence path (Linux), a previous run's evidence, a process left behind and a wall-clock jump. Not run against Oxylabs |
| A replay's missing, unreadable, malformed or invalid saved responses (T05; 1.7.3) | **SYNTHETIC TEST**: tested offline on Windows, in process and in a separate process with the network closed and sentinel credentials in its environment |
| A Classic request | **NOT TESTED**: none was made. That needs the account owner's credentials, entitlement, rates and approval |
| Listing pagination for Mariano's | **NOT AVAILABLE**: the documentation gives `marianos_search` no page parameter, so no second page is planned (see below) |

## What this build will not do

- Send a request. `IsolatedHttpTransport` refuses to be built for any target but a loopback test stub while `gates.LIVE_ENABLED` is `False`, and its worker (`networker.py`) refuses again. Changing that takes a code change, a new version and the owner's approval.
- Read a credential. `live` lists what a campaign still lacks, and it refuses before any credential is looked at.
- Probe an account. There are no automatic balance, usage, entitlement, authentication or qualification calls. The documented usage endpoint is never called.
- Use another service's results to qualify Classic. Results of the collectors' providers (the Oxylabs Web API included) say nothing about Classic.
- Assume pagination, store targeting or broader access works. Every one of them is checked in the response itself.
- Present a first page as category coverage. Page 1 of a Mariano's search is a sample of a store's assortment, nothing more.

## Install and check (offline)

```
uv sync --frozen
uv run pytest
uv run ruff check src tests
uv run mypy
```

The tests close the network: any attempt to open a socket or resolve a name fails the test that made it. They also remove the two credential variables from their environment.

Some tests run on one platform only, and say why when skipped:

- On Windows: the FIFO tests (`test_c2_a_fifo_at_the_evidence_path_...`, `test_a_fifo_is_refused_...`), because Windows has no FIFO in its file system, and the link test (`test_a_link_at_the_evidence_path_...`), because making a symbolic link needs a privilege a normal Windows account lacks. The refusal of a folder, an oversized file, a stale manifest and a left-behind process runs on both.
- On Linux and macOS: the write-through rename test (`test_c4_on_windows_...`), the Windows form of a synced rename.
- Anywhere: the two checks that the vendored readers are still the collectors' files skip when a collector's source is not beside the probe (a probe-only extraction), or is a later release than the one copied (each copy is still checked against its recorded git object).

## Commands

All commands are offline. `classic-probe --help` and `python -m classic_probe --help` show the same list.

| Command | Reads | Writes | Sends |
| --- | --- | --- | --- |
| `plan --targets config/targets.json [--rates FILE]` | the targets, an optional rate card | nothing | nothing |
| `validate --targets config/targets.json [--rates FILE]` | the same | nothing | nothing |
| `campaign-init --manifest M --ledger L --campaign-id ID [--offline]` | nothing | a new ledger and its manifest (refuses to replace either) | nothing |
| `status --manifest M` | the ledger | nothing | nothing |
| `confirm-charge --manifest M --seq N --value V --unit U --basis TEXT` | the ledger | one confirmed charge, with where it was read | nothing |
| `export --manifest M --out DIR` | the ledger | `ledger_export.json` | nothing |
| `replay --targets T --fixtures DIR --rates FILE --out DIR [--retailer walmart\|marianos]` | saved responses, checked before anything is written (1.7.3) | a new offline ledger and the evidence; nothing when an input is refused | nothing (OFFLINE REPLAY) |
| `live --manifest M [--approval F] [--entitlement F] [--rates F]` | those files | nothing | nothing: always refused in this build |

`plan` and `validate` cover both retailers. Exit codes: `0` ok, `2` refused input, `3` live refused, `4` the campaign stopped, `5` evidence export failed.

## The campaign limits (proposed; ceilings, never raised)

These are the limits of the Walmart probe 1.5.2, unchanged.

| Limit | Value | Enforced by |
| --- | --- | --- |
| Requests per retailer | 10, including setup, authentication or qualification calls, every retry and every restart | `Ledger.reserve`: the 11th is never reserved |
| Requests for both retailers | 20 | the same check, across both retailers |
| Campaign time | 30 minutes for the combined campaign, from its first reservation | each reservation must end before the end less 3 minutes kept for evidence export and cleanup. Of those 3 minutes, the last 30 s are a supervisor's: the session's own ledger writes end before them (1.7.1) |
| Provider charges | USD 5.00 combined, less USD 0.50 of headroom for delayed or uncertain charges | each request reserves its worst-case charge. Each retailer's share is USD 2.25 and is not borrowed |

A request exists in the ledger before it is sent:

1. `BEGIN IMMEDIATE` serializes concurrent invocations.
2. Each request reserves its worst-case charge before it leaves.
3. The reservation stays until the owner records a confirmed charge with its basis.

So a crash after a reservation, a request with no answer and a response the documentation says is not billed all keep their reservation. A row is never deleted and a reservation never changes; database triggers refuse both. The first stop stays the campaign's reason.

What keeps a second execution from granting itself a fresh budget:

- `open` never creates a ledger.
- Every ledger has a random genesis id, and the owner's approval must name it.
- A ledger is bound to its host.
- A path on a network share is refused.
- The Mariano's steps use the same ledger as the Walmart steps (`MarianosCampaign` is a `Campaign` with another adapter, not a second ledger).

## The Walmart steps

[docs/PAYLOAD_MATRIX.md](docs/PAYLOAD_MATRIX.md) has each payload in full.

1. `walmart-search-p1`: `walmart_search` for the store's Pickup results, with `?type=raw,parsed`.
2. `walmart-search-p2`: the same with `start_page: 2`, sent only when page 1's `last_visible_page` shows a page 2.
3. `walmart-product`: `walmart_product` for page 1's first non-sponsored Walmart.com product with a Pickup line.
4. `walmart-category-url`: a required category page by its URL alone. The documentation states no store or fulfillment parameter for this form. It is last because a page for any other store stops the campaign.

Store, fulfillment and identity are read from Walmart's own page data in the raw result. The readers are the Walmart collector's validated readers, vendored unchanged in `src/classic_probe/vendor/` (`VENDORED.json` has their origin and SHA-256). The parsed result has to agree with them.

## The Mariano's steps (added in 1.6.0)

1. `marianos-search-p1`: `marianos_search` for `cereal` with `store_id` `53100502` and `fulfillment_type` `pickup`. Mariano's documentation names no `parse` for its sources and returns the page HTML in `content`, so one result is reserved.
2. `marianos-product`: `marianos_product` for page 1's first ranked product (a sponsored placement is never chosen), the same store and Pickup. The documented `product_id` is the 13-digit product ID.
3. `marianos-category-url`: `https://www.marianos.com/pl/cereal-granola/03001` by its URL alone. The documentation states no store or fulfillment parameter for this form; a page for another store or fulfillment stops the campaign, so it is last.

**Not planned: any second page.** `marianos_search` documents no `start_page` or `pages`, and a listing URL with `page=2` could only be sent by URL alone, without the store. Listing pagination through Classic is an open gap, stated in the plan output (`not_planned`) and in [docs/DOCUMENTED_CONTRACT.md](docs/DOCUMENTED_CONTRACT.md).

What a Mariano's page shows is read from its own page state (`window.__INITIAL_STATE__`) with the Mariano's collector's reader, vendored unchanged (`vendor/marianos_initial_state.py`; its sanitizer `vendor/marianos_sanitize.py` with one import line rewritten, recorded in `VENDORED.json`):

- the shopper's selected store and modality (`getModalityPreferences`): must be 53100502 and `PICKUP`;
- the search's own request (`search.searchAll.requestVars`): `locationId` 53100502, `activeModalityType` `PICKUP`, page 1;
- each product's `price.storePrices.sourceLocationId`: any other store stops the campaign;
- for the product page, the requested product must be in the page's own product data, its prices for 53100502.

A refusal page (the collector's challenge markers), a retailer status that is not 2xx, a page without page state, an empty first page or a page for another product stops the campaign, and nothing more is sent.

## Evidence on disk (1.7.2)

| Where, in the campaign's output folder | What | Exported |
| --- | --- | --- |
| `response_NNN.json.gz`, `response_NNN.meta.json` | each answer's kept copy (sanitized) and its record, indexed in the ledger | yes |
| `campaign_evidence.json` | the session's own manifest, written from the durable index; it names its execution (1.7.2) | yes |
| `campaign_evidence.recovered.json` | the manifest of a supervisor's recovery, always marked incomplete | yes |
| `private/raw/dispatch_NNN.body`, `.status.json`, `.partial` | each answer as received, the worker's status for it (naming its dispatch, its declared length and whether it is complete; 1.7.2), or the part of a body that arrived, a body shorter than declared included | **no**: kept for the recovery and the account owner only, owner-only on Linux and macOS |

## Files

| Path | What |
| --- | --- |
| `config/targets.json` | the two retailers. Walmart #3891 Waukegan, Pickup, store verified from Walmart's own data. Mariano's Vernon Hills 53100502, Pickup: a lead from Kroger's certification Locations API, verified from the page state of the Mariano's collector's Web API requests of 2026-11-02 (not from Classic) |
| `config/*.example.json`, `.env.example` | placeholders only. No rate, approval, entitlement or credential ships with the probe; the Mariano's rates in `rates.example.json` are `null` |
| `docs/DOCUMENTED_CONTRACT.md` | what the documentation says, page by page, with the SHA-256 of each saved page |
| `docs/PAYLOAD_MATRIX.md` | every request the plan can send, with its reserved upper bound and its stop conditions |
| `CLASSIC_TEST_PLAN.md` | the staged plan for a future approved campaign |
| `tests/` | the offline tests. Their Classic envelopes are SYNTHETIC; `tests/captures_marianos/` holds the two real Mariano's pages they wrap |
