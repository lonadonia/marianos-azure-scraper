# Evidence of release 1.9 (2026-11-06 to 2026-11-09)

Collector **1.9.0rc4** ([`source/`](../../source/)) and the shared Classic probe **1.7.3**
([`classic-probe-1.7.3/`](../../classic-probe-1.7.3/)). The report that cites these files is
[`review/TECHNICAL_REPORT_1.9.0.md`](../../review/TECHNICAL_REPORT_1.9.0.md). Times are UTC.

Every live request of this task was sent on **2026-11-06** and **2026-11-09** from Hamza's workstation through Hamza's
Oxylabs Web API trial account, each reserved beforehand in the one ledger shared with the Walmart project
([`budget/`](budget/)). Nothing ran on the client's Azure VM, and the client's account was not used.

**What is published.** For O1 and O2: each request as sent (a request body never holds a credential: the key travels
in the provider's authentication header and is in none of these files) and each answer's metadata (status, the
provider's request id, time, sizes, hashes). For the collector stages: the console logs, the stage runner's record of
each invocation (`run.jsonl`), the ledger stage record with command, configuration hashes, revision, objective,
ceilings, deadline, retry policy and stop conditions (`stage.json`), and each run's database rows
(`run_<id>/db/*.csv`) and exports (`run_<id>/exports/`). Every run here was rejected by its own gates (report §11), so
its export is evidence, not a publication. Also published: the analyses, the reproductions, the test sessions, the
tools that produced them and every Mariano's row of the ledger.

**What is kept privately by Hamza.** The provider's raw answers, which carry account metadata, and the pages and
product data the collector stored. Each is listed with its size and SHA-256: O1's and O2's answers in
`RAW_ANSWERS_SHA256.csv`, a run's stored files in `run_<id>/STORED_PAGES_SHA256.csv` (with its `provenance.json`,
each record's sources, 3.9 to 6.7 MB a run). The pages used as test fixtures are published, sanitized, under
[`source/tests/fixtures/`](../../source/tests/fixtures/), each with its origin and both hashes (`SOURCES*.json`).

**What was changed for publication.** The provider key's fingerprint is written `<key fingerprint>`, the Windows user
folder `<user>` and the workstation's projects folder `<projects>`; cp1252 bytes 0x9B ("›") in console logs are
written as UTF-8; the saved-page paths of `BINDING_SCAN.csv` are made relative to this repository. Each changed file
is in [`manifests/REDACTIONS.csv`](../../manifests/REDACTIONS.csv) with its original and published SHA-256. Logs
otherwise keep the workstation's working folders (`C:\m8\...`) as written.

## Live stages of 2026-11-06 (shared trial ledger, campaign `oxylabs-trial-20261103`)

| Folder | Stage, time, revision | What it shows | Requests, cost |
|---|---|---|---|
| [`live/O1/`](live/O1/) | `M-O1-terms-offers-190-20261106`, 18:35-19:17Z; requests sent by [`tools/observe190.py`](tools/observe190.py) with the collector's Oxylabs client at development commit `51db61d` (its version string then still read 1.8.0rc5) | M4: the coupons API failed twice (HTTP 500, not charged); the product's own page holds complete terms, and its coupons load only when the provider renders it: 1 of 14 product pages came back rendered ([`PDP_SUMMARY_01-13.json`](live/O1/PDP_SUMMARY_01-13.json)). M6: the named offers and sizes re-observed | 16 sent, 14 results, USD 0.021 |
| [`live/S1/`](live/S1/) | `M-S1-canary-catfood-190-20261106`, 19:33-19:36Z; collector **1.9.0rc1** `b0f9191`, run `01M6S5MYBC05W3S308EC7XWTGV`, by [`tools/live190_run.py`](tools/live190_run.py) | Store and PICKUP verified; Cat Food page 1 read three times and refused each time (the page state listed 24 products, rc1's grid parser found none): the site's new tile. The run stopped as `ABNORMAL_RESULT` (exit 6) and was rejected; no record was accepted | 5 sent, 5 results, USD 0.0075 |
| [`live/O2/`](live/O2/) | `M-O2-tile-discovery-190-20261106`, 19:45-19:51Z; `tools/observe190.py` with the 1.9.0rc1 tree | The new tiles on listing and search pages; a rendered listing answer carries no tiles; no tile shows a coupon | 7 sent, 7 results, USD 0.0105 |

On 2026-11-06, **28 submissions, 26 results, USD 0.039** (settled at the reservation rate, USD 0.0015 per result; the
two HTTP 500 answers settled at 0 as documented free). No row is held or unknown.

## Live stages of 2026-11-09 (Hamza's approval: at most 295 submissions, USD 0.4425)

Each collector stage was run by [`tools/live190_run.py`](tools/live190_run.py) under the shared ledger, one listing
lane unless stated, store 53100502 PICKUP verified on every check. Configurations: [`tools/prep_stages_190rc3.py`](tools/prep_stages_190rc3.py)
and [`tools/prep_stages_190rc4.py`](tools/prep_stages_190rc4.py) (the shipped configuration plus the changes each stage
states).

| Folder | Stage, time, revision, run | What it shows | Submissions, USD settled |
|---|---|---|---|
| [`live/S1b/`](live/S1b/) | `M-S1b-canary-catfood-190rc3-20261109`, 12:36-12:39Z, 1.9.0rc3, `01M704YFEYRM4ZD5WNW3S7WVH8` | the canary on the new tile; Cat Food page 2 repeated page 1; 8 product-terms reads, 2 rendered (report §6) | 13, 0.0195 |
| [`live/S4/`](live/S4/) | `M-S4-rows22-27-190rc3-20261109`, 14:30-14:38Z, 1.9.0rc3, `01M70BG79WGW9EC5ZTW2M4V4XS` | rows 22-27: 552 fresh valid; 8 listings stopped at a repeated page; rejected by G3 only | 43, 0.0645 |
| [`live/S5a/`](live/S5a/) | `M-S5a-rows23-26-one-lane-190rc3-20261109`, 14:41-14:45Z, 1.9.0rc3, `01M70C404FTCMYSY621EKJ015X` | rows 23-26 with one lane: 306 fresh valid | 19, 0.0285 |
| [`live/S5b/`](live/S5b/) | `M-S5b-rows23-26-two-lanes-190rc3-20261109`, 14:46-14:52Z, 1.9.0rc3 with two lanes, `01M70CD8PJQS3QDMWR5AXPS39P` | signal, resume, refused second start, hard kill, resume ([`s5b_steps.json`](live/s5b_steps.json)); rejected by G13: the two-lane defect N17 (report §10) | 20: 17 settled (0.0255), 3 unknown held (0.0045) |
| [`live/S3/`](live/S3/) | `M-S3-milk-brand-union-190rc3-20261109`, 14:56-14:57Z, 1.9.0rc3, `01M70CYWNRZNS4NCZVDX2X13XK` | Milk states 246 (inside the window): no brand reading planned; 77 of 246 read | 6, 0.009 |
| [`live/S5b2/`](live/S5b2/) | `M-S5b2-rows23-26-two-lanes-190rc4-20261109`, 15:15-15:19Z, 1.9.0rc4 with two lanes, `01M70E1GNA85H05HDM45F5XQRS` | the same steps on 1.9.0rc4 ([`s5b2_steps.json`](live/s5b2_steps.json)): G13 passes; no completed page asked again | 17: 13 settled (0.0195), 4 unknown held (0.006) |
| [`live/S4b/`](live/S4b/) | `M-S4b-rows22-27-190rc4-20261109`, 15:52-15:58Z, 1.9.0rc4, `01M70G5ZEPFG1GVT2H5QWPVQKJ` | rows 22-27 again: every page 2 repeated page 1; 243 fresh valid | 32: 31 settled (0.0465), 1 provider failure settled free |
| [`live/S4c/`](live/S4c/) | `M-S4c-rows1-21-small-listings-190rc4-20261109`, 16:00-16:10Z, 1.9.0rc4, `01M70GKE2KJF0D6CKSY04VD8YK` | 31 listings of rows 1-21: **700 distinct fresh valid products**, the final revision's qualification count; rejected by G3 only | 59, 0.0885 |
| [`live/S3b/`](live/S3b/) | `M-S3b-natural-frozen-brand-union-190rc4-20261109`, 16:12-16:14Z, 1.9.0rc4, `01M70H9RB4Q736926MP3W5117A` | Frozen (273 products, above the window): page 1 in form B, no brand reading possible; page 2 repeated. Its closed ledger outcome is corrected in report §4 | 4, 0.006 |
| [`live/S4d/`](live/S4d/) | `M-S4d-rows1-21-single-page-listings-190rc4-20261109`, 16:20-16:25Z, 1.9.0rc4, `01M70HRZQX1KXHZQVNMS1KDCPK` | the 30 single-page listings of rows 1-21 in the queue: 29 done; 294 fresh valid | 35, 0.0525 |

On 2026-11-09, **248 submissions**: 240 results settled (USD 0.360), 1 provider failure settled free, 7 unanswered
submissions held as unknown at their worst case (USD 0.0105). 47 submissions of the approval were left unused.

**Across the stages of 2026-11-09:**

| File | What it holds |
|---|---|
| [`live/PAGING_CENSUS_190.csv`](live/PAGING_CENSUS_190.csv) | every listing-page answer of the ten runs (208): time, page asked, the provider's request id and rendering, the products' ranks, the search id, the stated counts, whether the brand filter is in the page state (the answer's form, report §3.2), and its class against the listing's earlier pages |
| [`live/INCOMPLETE_QUEUE_190.csv`](live/INCOMPLETE_QUEUE_190.csv) | the exact queue after the last stage: every listing of the shipped CSV, its size in the census of 2026-11-02, its latest 1.9 state, what is still needed, and the 1.9 stages that completed it |
| [`live/PAGING_REPEAT_O2_S1b.jsonl`](live/PAGING_REPEAT_O2_S1b.jsonl) | the first repeats: page 1 against ?page=2/3 in O2's answers (2026-11-06) and S1b's pages, products by rank |
| [`live/s5b_steps.json`](live/s5b_steps.json), [`live/s5b2_steps.json`](live/s5b2_steps.json) | each interruption step's UTC times, exit code and ledger counts |
| [`live/release_hold_20261109.log`](live/release_hold_20261109.log) | the release of S1's hold before S1b (no request) |

## Analyses, reproductions and identities

| Folder | What it holds |
|---|---|
| [`m2_binding/`](m2_binding/) | M2: what each of 99 saved pages of 2026-11-02 states about its own search (filter, store, fulfillment, search ids, loading state) |
| [`m3_ppm/`](m3_ppm/) | M3: the two price-per-measure examples traced to their card nodes and page-state values, with excerpts and hashes; the 54 Q2 records the 1.9 anomaly rules flag |
| [`m4_energizer42/`](m4_energizer42/) | M4: the 42 Energizer records' cards in Q1c and in Q2 |
| [`m5_catfood/`](m5_catfood/) | M5: Cat Food's 10 pages and 232 slots in Q2, and the product shown twice |
| [`repro/`](repro/) | T05 on probe 1.7.2 and 1.7.3; T06 on `ac114d7`; T07 on 1.8.0rc5 `ee5ec99`; N09 (a tile's coupon) on 1.9.0rc2 and rc3; N17 (two lanes) on 1.9.0rc3 and rc4. Each failing case is shown failing by its output |
| [`m10_identity/`](m10_identity/) | M10: the Mariano's Classic adapter's blob, the trees of probes 1.6.0 and 1.7.3, and the vendored files, computed from git |
| [`tests/`](tests/) | the test sessions of the delivered trees: unit 488 passed and integration 183 passed on 1.9.0rc4 ([`wt_rc4_unit.log`](tests/wt_rc4_unit.log), [`wt_rc4_integration.log`](tests/wt_rc4_integration.log)); ruff, format and mypy clean ([`wt_rc4_lint.json`](tests/wt_rc4_lint.json)); probe 1.7.3: 222 passed, 5 skipped ([`probe173_clean.log`](tests/probe173_clean.log)); [`RUNS.jsonl`](tests/RUNS.jsonl) records each session's revision, clean tree, counts and log hash; [`mutants_190.json`](tests/mutants_190.json) the three remaining mutants of 1.8.0rc5's plan |
| [`budget/`](budget/) | the shared ledger at publication time ([`LEDGER_STATUS.json`](budget/LEDGER_STATUS.json): campaign and per-project totals, every Mariano's stage with its closed outcome, hash chain verified) and every Mariano's row ([`LEDGER_ROWS_MARIANOS.csv`](budget/LEDGER_ROWS_MARIANOS.csv)); [`NEXT_STAGES.json`](budget/NEXT_STAGES.json), the proposed next live stages with their ceilings |
| [`tools/`](tools/) | the scripts that produced these files |
