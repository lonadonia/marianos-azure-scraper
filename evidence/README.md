# Evidence of the 1.10.0rc6 delivery

Everything here was produced on 2026-11-17 on Hamza's own Azure test VM (Ubuntu 24.04, PostgreSQL 16, Python 3.12), not
on the client's VM, by the candidate **1.10.0rc6** (`d77f306`) as installed there; the earlier stages of this
review (F2, the pilots and publication tests on 1.10.0rc3 to 1.10.0rc5) are in the earlier deliveries' tags
([`../EARLIER_DELIVERIES.md`](../EARLIER_DELIVERIES.md)). Live requests went to the Oxylabs Web API on the new
credential's USD 5 of free credit, each one reserved in this delivery's own ledger before it was sent
([`ledger/`](ledger/README.md)). Nothing here is a fixture or a replay presented as live: the offline items say so
where they appear.

**What the published copy changes.** Private identifiers (the VM's host name and address, its admin user and home
folder, the workstation's name and folders, the credential's fingerprint beyond its last six characters) are
masked, in any letter case, and nothing else. Every masked file is listed in
[`manifests/REDACTIONS.csv`](../manifests/REDACTIONS.csv) with what was masked; every file's origin is in
[`manifests/FILE_MAP.csv`](../manifests/FILE_MAP.csv). For an unchanged file the original's SHA-256 is its
published one. For a masked file it is **withheld**: the masked values are short and guessable, and the hash of
the unmasked file would let a guess be confirmed offline. In its place `original_commitment` is an HMAC-SHA256 of
the unmasked file under a private key: shown the key and the original on request, anyone can check that the
original is the one this publication committed to, and without the key it confirms nothing.

The stored pages (the provider's answers) stay private: each run lists them by SHA-256 in
`STORED_PAGES_PRIVATE.csv`, and every exported record names the page it was read from by the same hash (they hold
no private identifier; the scan of every stored page found none). Files above 8 MB are gzipped (`COMPRESSED.csv`
gives the uncompressed SHA-256).

| Folder | What it holds |
|---|---|
| [`runs/`](runs/) | One folder per live stage, each with its `RUN_REPORT.md` (below) |
| [`coverage/`](coverage/README.md) | The full run against the 1.9 baseline queue, listing by listing (302 product listings and the Coupons route); the listings above the site's window; the re-asks and repeated pages by hour |
| [`publication/`](publication/README.md) | The full run's publication, or the collector's refusal with the published dataset unchanged |
| [`operations/`](operations/README.md) | The refused second start, the planned stops and resumes, the hard kill and its recovery, the check that no completed page was asked again, the finalized run R6 and its refused publication |
| [`accuracy/`](accuracy/README.md) | The client's named checks traced to the stored pages: the four product pages, Cat Food 27021, the two PPM traces, the offer and size examples, the Coupons row |
| [`samples/`](samples/README.md) | For checking records against their source without the VM: records of the full run with the tile each was read from, and `check_sample.py` |
| [`estimate/`](estimate/README.md) | The request, cost and runtime estimate of the full run, reprojected after each slice, and the funding gap |
| [`validation/`](validation/README.md) | OR-20: the export validation of F2's 575 pages by the installed 1.10.0rc6 and its recorded differences, one by one |
| [`install/`](install/README.md) | Build, installation on the same target as 1.10.0rc5, migrations, backup and restore check, rollback, identity; the container image and its checks |
| [`tests/`](tests/README.md) | The candidate's suites; each correction's tests before and after |
| [`ledger/`](ledger/README.md) | This delivery's spending ledger: every stage and reservation, the hash-chained event log and how to check it |
| [`walkthrough/`](walkthrough/README.md) | The recorded walkthrough of 1.10.0rc6 on Hamza's VM: the recording, its video, each step's raw output |
| [`tools/`](tools/README.md) | The operator's tools used for these stages, and the check that the copies installed on the VM are these |

## The runs

| Folder | Stage | What it is | Result |
|---|---|---|---|
| [`P7/`](runs/P7/RUN_REPORT.md) | P7 | a one-lane pilot of 1.10.0rc6 (rows 0 and 27: the Coupons route and the cat food row's listings), never a complete catalogue, never published (1.10.0rc6) | rejected; gates FAIL: G3, G14; 46 fresh valid |
| [`R6a/`](runs/R6a/) | R6a | the first slice of the full run R6 (every row, rows 22, 27, 23 to 26 and 15 first, the four product pages named), stopped at its ceiling at the site's busiest repeat hour (1.10.0rc6) | interrupted |
| [`R6fin/`](runs/R6fin/RUN_REPORT.md) | R6 (finalized) | R6 finalized without a request: validated and exported as an incomplete run, so R7 starts on its own (1.10.0rc6) | rejected; gates FAIL: G3, G4, G14; 448 fresh valid |
| [`R7a/`](runs/R7a/RUN_REPORT.md) | R7a | the full run R7's first slice (two lanes; rows 22, 27, 23 to 26 and 15 first; the four product pages named), from 03:00Z (1.10.0rc6) | interrupted |
| [`R7a2/`](runs/R7a2/RUN_REPORT.md) | R7a2 | R7's second slice: a resume from 04:00Z (the watcher's repeat rule had stopped R7a) (1.10.0rc6) | interrupted |
| [`P8/`](runs/P8/) | P8 | a one-lane pilot of 1.10.0rc6 on an isolated target of its own (R7 left resumable on its target), from 04:20Z: Dog Food 27017 and Hardware 33, to read again the three named product pages R7 had got unrendered; validated as a pilot, never published (1.10.0rc6) | validated |
| [`R7b/`](runs/R7b/RUN_REPORT.md) | R7b | R7's third slice, from 04:35Z: a hard kill (SIGKILL) of the worker after 15 collected pages, then the recovery of the same run in the same stage (R7b2, once the dead lease expired), until the repeat rule stopped it (1.10.0rc6) | interrupted |
| [`R7w/`](runs/R7w/RUN_REPORT.md) | R7w | R7's fourth slice, from 05:05Z: the recorded walkthrough, the operator's controls on the live run (a SIGTERM stop, a refused second start, a resume, a refused publication) (1.10.0rc6) | interrupted |
| [`R7c/`](runs/R7c/RUN_REPORT.md) | R7c | R7's fifth and last slice, from 05:22Z, capped at 150 submissions: two executions (the second a resume in the same stage), each stopped about 5 minutes in when Hard Cider 08194 failed again (OR-22, OR-23); no further resume once the stage's repeat share (8 of 18 page-2+ answers) was above the rule (1.10.0rc6) | interrupted |
| [`R7fin_copy/`](runs/R7fin_copy/RUN_REPORT.md) | R7fin_copy | R7's state at the end of R7c, finalized in an isolated copy of the target with no provider request (checks, gates, exports; its publication refused); R7 itself left interrupted and resumable on the target (1.10.0rc6) | rejected; gates FAIL: G3, G4; 2,518 fresh valid |

Each run folder holds: `stage_record.json` (the stage as approved: command, ceiling, revision, configuration hashes),
`RUN_REPORT.md` and `RUN_FACTS.json`, the dataset as exported (`export/`: products, products_fresh, provenance of every
record, memberships, offers, coverage by listing and by CSV row, the listing pages, the requests set aside, the
validation report and manifest), the database rows of the run (`db_*.csv`: pages answered and their verdicts, page
fetches, events, segments, store checks, validation findings, exports, publications), `ledger_reservations.csv`,
`ledger_stage.json` and `ledger_chain.txt`, the harness record (`harness_runs.jsonl`), the operator's watch log and
the complete journal of each execution, and `analysis/` (per-listing coverage, re-asks and their waits, store
checks). A slice that ended interrupted has no export of its own (an unfinished run is not exported): a run's
export is in the folder of its finalization, `R6fin/` for R6 and `R7fin_copy/` for R7 (R7 finalized offline in an
isolated copy of its target; R7 itself stays interrupted and resumable), whose `RUN_REPORT.md` covers all the
run's slices.

A run with any command-line narrowing (`--categories`, a limit) is a **pilot**: exported, never published (P7).
`--rows-first` only orders the plan and `--term-upc` only names the product pages to read; neither narrows the scope,
so R6 and R7 are full-scope runs.
