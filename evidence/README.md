# Evidence of the 1.10.0rc5 delivery

Everything here was produced on 2026-11-16 on Hamza's own Azure test VM (Ubuntu 24.04, PostgreSQL 16, Python 3.12), not
on the client's VM, by the collector revision each run names: **1.10.0rc3** (S6, S6b), **1.10.0rc4** (L1, L2, P1 to
P3, F1) and **1.10.0rc5**, the final candidate (`bc19afe`: F2, P4 to P6, and the walkthrough). Live requests went
to the Oxylabs Web API on Hamza's trial credit, each one reserved in the shared trial ledger before it was sent.
Nothing here is a fixture or a replay presented as live: the offline items say so where they appear.

What the published copy changes: private identifiers (the VM's host name and address, home folders, the key file's
path, the ledger lease holder's host tag) are masked, and nothing else; each change is listed in
[`manifests/REDACTIONS.csv`](../manifests/REDACTIONS.csv) and every file's origin and original SHA-256 in
[`manifests/FILE_MAP.csv`](../manifests/FILE_MAP.csv). The stored pages (the provider's answers) stay private:
each run lists them by SHA-256 in `STORED_PAGES_PRIVATE.csv`, and every exported record names the page it was read
from by the same hash. Files above 8 MB are gzipped (`COMPRESSED.csv` gives the uncompressed SHA-256).

| Folder | What it holds |
|---|---|
| [`runs/`](runs/) | One folder per live stage, each with its `RUN_REPORT.md` (below) |
| [`coverage/`](coverage/README.md) | The full run F2 against the 1.9 baseline queue, listing by listing (302 product listings) |
| [`publication/`](publication/README.md) | P4 to P6 on 1.10.0rc5, on an isolated target: a publication, a refused one with the published files unchanged, a second publication and its rollback (and P1 to P3, the same on 1.10.0rc4) |
| [`operations/`](operations/README.md) | Within the full run F2, under two lanes: the refused second start, the VM reboot between two slices, the hard kill and its recovery, the SIGTERM stops and resumes, the check that no completed page was asked again; the comparison of one and two lanes |
| [`accuracy/`](accuracy/README.md) | The client's named checks traced to the stored pages: Cat Food 27021, the two PPM traces, the four digital-coupon examples, the offer and size examples, and the Coupons row (a defect found in this review) |
| [`samples/`](samples/README.md) | For checking records against their source without the VM: each record of an export with the tile it was read from, and `check_sample.py` |
| [`estimate/`](estimate/README.md) | The full-cycle request, cost and runtime estimate updated from these runs, and the shortfall |
| [`install/`](install/README.md) | Build, installation, migrations, backup, restore check, rollback and forward again; the container image and its checks |
| [`tests/`](tests/README.md) | The candidate's suites, the 1.10.0rc5 fix before and after, the offline before/after of C1 and of the publication result on 1.9.0rc4, and 1.10.0rc4's records |
| [`ledger/`](ledger/README.md) | The trial ledger: every reservation of these stages, the hash chain check, and the account of the trial credit |
| [`walkthrough/`](walkthrough/README.md) | The recorded walkthrough of 1.10.0rc5 on Hamza's VM: the recording, its video, each step's raw output and the steps (the tools are in `tools/`) |
| [`tools/`](tools/README.md) | The operator's tools used for these stages (the gate, the stage launcher, the watcher, the evidence collector, the analyses) |

## The runs

| Folder | Stage | What it is | Result |
|---|---|---|---|
| [`S6/`](runs/S6/RUN_REPORT.md) | S6 | rows 22 to 27, one lane: C1 on the live site (1.10.0rc3) | rejected; gates FAIL: G3; 1,141 fresh valid |
| [`S6b/`](runs/S6b/RUN_REPORT.md) | S6b | row 10, Natural Organic › Frozen (18010), above the 250-result window (1.10.0rc3) | validated; gates FAIL: G14; 279 fresh valid |
| [`L1/`](runs/L1/RUN_REPORT.md) | L1 | rows 22 to 27, one lane (lanes comparison) (1.10.0rc4) | validated; gates: all PASS; 1,138 fresh valid |
| [`L2/`](runs/L2/RUN_REPORT.md) | L2 | rows 22 to 27, two lanes (lanes comparison) (1.10.0rc4) | rejected; gates FAIL: G3; 1,018 fresh valid |
| [`P1/`](runs/P1/RUN_REPORT.md) | P1 | publication test (isolated target): a complete run, published (1.10.0rc4) | published; gates FAIL: G14; 62 fresh valid |
| [`P2/`](runs/P2/RUN_REPORT.md) | P2 | publication test: a run stopped at its ceiling, its publication refused (1.10.0rc4) | rejected; gates FAIL: G3, G14; 47 fresh valid |
| [`P3/`](runs/P3/RUN_REPORT.md) | P3 | publication test: published, then rolled back (1.10.0rc4) | published; gates FAIL: G14; 62 fresh valid |
| [`F1a/`](runs/F1a/RUN_REPORT.md) | F1 | the full run of 1.10.0rc4 (1.10.0rc4) | stopped by the collector: STORE_NOT_VERIFIED (exit 7), rejected; 1.10.0rc5 asks such a page again |
| [`F2a/`](runs/F2a/) | F2a | full run F2, slice 1 (and the refused second start) (1.10.0rc5) | slice ended resumable (SIGTERM, exit 75); the run continues in the next slice |
| [`F2b/`](runs/F2b/) | F2b | full run F2, slice 2 (after the VM reboot) (1.10.0rc5) | slice ended resumable (SIGTERM, exit 75); the run continues in the next slice |
| [`F2c/`](runs/F2c/) | F2c | full run F2, slice 3 (hard kill and recovery) (1.10.0rc5) | slice ended resumable (SIGTERM, exit 75); the run continues in the next slice |
| [`F2d/`](runs/F2d/RUN_REPORT.md) | F2d | full run F2, slice 4 (the walkthrough; the collector stopped the run) (1.10.0rc5) | the whole run F2: stopped by the collector, STORE_NOT_VERIFIED (exit 7), not resumable: rejected; 7,678 fresh valid; records kept as a partial export, never published |
| [`P4/`](runs/P4/RUN_REPORT.md) | P4 | publication test on 1.10.0rc5: a complete run, published (1.10.0rc5) | validated; gates FAIL: G14; 62 fresh valid |
| [`P5/`](runs/P5/RUN_REPORT.md) | P5 | publication test on 1.10.0rc5: a partial run, publication refused (1.10.0rc5) | rejected; gates FAIL: G3, G4, G14; 22 fresh valid |
| [`P6/`](runs/P6/RUN_REPORT.md) | P6 | publication test on 1.10.0rc5: published, then rolled back to P4 (1.10.0rc5) | validated; gates FAIL: G14; 62 fresh valid |

Each run folder holds: `stage_record.json` (the stage as approved: command, ceiling, revision, configuration hashes,
approval), `RUN_REPORT.md` and `RUN_FACTS.json`, the dataset as exported (`export/`: products, products_fresh,
provenance of every record, memberships, offers, coverage by listing and by CSV row, the listing pages, the requests
set aside, the validation report and manifest), the database rows of the run (`db_*.csv`: pages answered and their
verdicts, page fetches, events, segments, store checks, validation findings, exports, publications),
`ledger_reservations.csv` and `ledger_chain.txt`, the harness record (`harness_runs.jsonl`), the operator's watch
log and the complete journal of each execution, and `analysis/` (per-listing coverage, re-asks and their waits,
store checks). A slice that ended interrupted has no export of its own (an unfinished run is not exported): the
run's export is in its last slice's folder.

A run with any command-line narrowing (`--categories`, a limit) is a **pilot**: exported, never published. The
full-scope runs F1 and F2 have none; they were read in slices because the trial credit cannot complete them. F1
(1.10.0rc4) was stopped by the collector with `STORE_NOT_VERIFIED` and rejected, which led to the 1.10.0rc5 fix. F2
(1.10.0rc5) was stopped by the collector the same way (`STORE_NOT_VERIFIED`, a narrower case: a page of the right
store whose product data had not loaded) and rejected; its records are kept as a partial export, which is never
published.
