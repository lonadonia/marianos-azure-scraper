# Operations under two lanes, and one lane against two

All on Hamza's VM, live, through the shared trial ledger's gate (every submission reserved before it is sent; the
gate allows at most as many in flight as the stage has lanes). The checks below ran on the final candidate
1.10.0rc5, during the slices of its full run F2 (two lanes). The comparison of one and two lanes ran earlier the same
day on 1.10.0rc4 (L1 and L2): 1.10.0rc5 changes one store check of a listing page and nothing in the lanes, the gate,
the ledger or the pagination (`git diff 570ff7c bc19afe`, [`../tests/rc5_fix/`](../tests/rc5_fix/)), and F2's own
slices give the two-lane measures of 1.10.0rc5 itself.

## The checks

| Check | Where | Expected | Observed | Record |
|---|---|---|---|---|
| Pause (a resumable stop) and resume | F2a, F2b, F2c | SIGTERM (`systemctl stop`) ends the execution with exit 75; the run stays interrupted and resumable; the next slice resumes the same run | each slice stopped by the operator's slice stopper at 190 reservations, exit 75 each; F2b, F2c and F2d resumed the same run `01M7JNB2HDFCNR3GHQVX8FYXX6` | `SLICE_STOP_F2a.log`, `SLICE_STOP_F2b.log`, `SLICE_STOP_F2c.log`; each run folder's `harness_runs.jsonl` |
| A second start refused before any paid call | F2a, 17:10:16Z, while the run was active | exit 9 (busy), no request, no reservation | exit 9 in 0.2 s ("has an unfinished run ... resume or finalize it"); the gate refused nothing because nothing was asked; all 190 of F2a's ledger rows belong to the running execution's lease (74): the refused start reserved nothing; again in F2d's walkthrough (exit 9) | `REFUSED_SECOND_START_F2a.log`; `../runs/F2a/ledger_reservations.csv`; `../walkthrough/` |
| A VM restart between slices | between F2a and F2b | services, database, ledger and the run's checkpoints identical before and after; the run resumes | reboot 17:33:01Z, up 17:33:11Z; run, tasks, listing pages, requests set aside, UPCs, segments, locks and ledger identical before and after; F2b resumed the run at 17:36:42Z | `REBOOT_BETWEEN_F2a_AND_F2b.log`, `REBOOT_STATE_BEFORE.txt`, `REBOOT_STATE_AFTER.txt` |
| Automatic resume after a provider-error pause | F2b, 17:38:56Z | after a provider error the run pauses at a checkpoint and resumes by itself after 60 s, at most 3 times a run | Crackers (01026) page 1 answered malformed three times (two in F2a, one in F2b: the page state lists 24 products and the grid shows 0 cards); at the third the run paused (PROVIDER_ERROR) and resumed automatically 60 s later (1 of 3); the fourth answer was read: 266 results, 250 reachable, read through 17 child listings | `AUTO_RESUME_F2b.txt`; `../runs/F2b/db_collection_segments.csv` |
| Hard kill and recovery under two lanes | F2c, 17:54:02Z | after SIGKILL the run is left running with leased tasks and a request in flight; once the dead lease expires, resume recovers the run, reclaims the tasks from their checkpoints, and keeps the request in flight as an unknown outcome charged against the ceiling | killed after 40 pages, with 2 tasks leased and 1 request dispatched; the dead lease (76) expired 17:55:52Z; resumed 17:55:58Z: RUN_RECOVERED, TASK_LEASE_RECLAIMED for both tasks, a new segment; the request became unknown (charged) | `KILL_RECOVER_F2c.log`; `../runs/F2c/` |
| Completed pages are not asked again | the whole run F2, every segment of the four slices | no completed request asked again, apart from C1's deliberate re-asks | 576 listing-page rows, 416 requests completed; 13 deliberate C1 re-asks of completed first pages for their filters (answers {'reasked/new': 12, 'refused/malformed': 1}); **0 re-fetched** | `NO_REFETCH_F2.txt` |
| At most as many requests in flight as lanes | every F2 slice (two lanes); L1 (one lane), L2 (two) | at most 2 with two lanes, 1 with one | peak 2 in every F2 slice and in L2, 1 in L1 | `PEAK_IN_FLIGHT.txt` (from the ledger rows) |
| Unknown outcomes kept and charged | every stop with a request in flight | a request whose outcome is unknown when its process stops stays charged at the worst case until reconciled | held as unknown: F2a 2, F2b 2, F2c 3, F2d 2 (F2c's include the request in flight at the kill) | each run folder's `ledger_reservations.csv`; `../ledger/` |
| A ceiling stop finalizes the run; its publication is refused | P5 (1.10.0rc5, isolated target) | at its ceiling the collector finalizes the run as a partial dataset (exit 4) and `publish` refuses it (exit 6), the published files unchanged | P5 stopped at its 4-submission ceiling (SPENDING_CEILING, exit 4), finalized as partial; publish exit 6; every section of the published state equal before and after | `../publication/` |
| The last slice to its ceiling (planned) | F2d (the walkthrough) | the run goes on to the slice's ceiling, where the collector finalizes it as a partial dataset (exit 4); `publish` refuses it (exit 6) | **not met**: F2d's executions ended with exit codes 75, 7: after the SIGTERM stop and the refused start, the collector stopped the run, not resumable, at 18:56:02Z (STORE_NOT_VERIFIED, the defect OR-19), 8 submissions into the resume; its publication refused with exit 6, nothing published | `STORE_STOP_F2.txt`, `../walkthrough/`, `../runs/F2d/` |

**How "not asked again" is checked** ([`../tools/no_refetch.py`](../tools/no_refetch.py), on the run's own `listing_pages` rows, every
segment): a request is its listing, partition, route, page and filter. After a request's completed row, any later row
of the same request is a re-fetch, unless the run set that request aside (C1) and the set-aside request itself names
that very row among its re-asks (`deferred_requests.attempts`, by listing-page id). That happens by design for a
listing's first page above the 250-result window that names no child listing and no brand: it is counted, then asked
again for its filters. The check's first version recognised a re-ask only by its state ("reasked") and, after F2c,
reported one re-fetch: the first of two such re-asks of Natural Organic › Grocery (18012) page 1, whose own answer
was malformed (state "refused"). The rule above, which matches the set-aside request's own record, replaced it; the
first version's output is kept as `NO_REFETCH_F2c_FIRST_RULE.txt`.

**F2's stop and its validation.** [`STORE_STOP_F2.txt`](STORE_STOP_F2.txt): the pages of F2's stop
(`STORE_NOT_VERIFIED`, 18:56:02Z), read offline with the installed collector's own functions
([`../tools/store_stop_check.py`](../tools/store_stop_check.py)): the stop page, its earlier answer, and a page of
the same shape that the check does not judge. [`VALIDATE_EXPORT_OOM_F2.txt`](VALIDATE_EXPORT_OOM_F2.txt): F2's
export validation killed by the kernel for lack of memory, with the contract check of both export files
([`F2_CONTRACT_CHECK_products.json.jsonl`](F2_CONTRACT_CHECK_products.json.jsonl),
[`F2_CONTRACT_CHECK_products_fresh.json.jsonl`](F2_CONTRACT_CHECK_products_fresh.json.jsonl)).

## One lane against two, on the same scope

L1 (one lane) and L2 (two lanes) read the same scope, CSV rows 22 to 27 (17 listings), with the same revision,
configuration and ceiling, 4 minutes apart. Measures from the ledger rows and the database, nothing estimated
([`LANES_L1_L2.json`](LANES_L1_L2.json), `q5_compare.py`):

| Measure | L1, one lane | L2, two lanes |
|---|---|---|
| Submissions | 73 | 72 |
| USD settled | 0.1 | 0.1 |
| Unknown outcomes | 0 | 0 |
| Wall time (s) | 1139.6 | 1166.2 |
| Seconds with a request in flight | 575.1 | 390.8 |
| Seconds with none in flight (re-ask waits) | 564.5 | 775.4 |
| Peak requests in flight | 1 | 2 |
| Pages answered | 69 | 68 |
| Pages counted | 58 | 52 |
| Requests set aside | 8 | 9 |
| Re-asks | 11 | 12 |
| Listings | {"DONE": 15, "EMPTY": 2} | {"DONE": 13, "EMPTY": 2, "INCOMPLETE": 2} |
| Verified records | 1138 | 1018 |
| Status | validated | rejected |

On this scope both runs end on C1's waits (a request set aside is asked again at least 300 s after its previous answer), so the wall time is about the same; the time spent with a request in flight falls from 575.1 s to 390.8 s with two lanes, and the gate never let more requests fly than the stage's lanes. L2 left two listings incomplete where L1 completed them: their re-asks were answered with the repeated page again, an answer of the site, not of the lane count. The full run F2 ran with two lanes throughout (its slices' measures are in the estimate).
