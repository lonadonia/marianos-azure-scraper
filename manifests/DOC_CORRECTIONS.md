# Documentation corrections for this publication

## Release 1.9.0rc4 (2026-11-09, tag `review-1.9.0rc4-20261109`)

The 1.8.0rc5 documents stay as they were published on 2026-11-02 (tag `review-1.8.0rc5-20261102`); 1.9 adds its own
([`review/TECHNICAL_REPORT_1.9.0.md`](../review/TECHNICAL_REPORT_1.9.0.md),
[`review/CORRECTION_MAP_1.9.0.csv`](../review/CORRECTION_MAP_1.9.0.csv),
[`review/AUDIT_29_RECONCILIATION.csv`](../review/AUDIT_29_RECONCILIATION.csv)) and changes the shared ones as listed
here. Old run versions and counts are not rewritten.

| Change | Where | Basis |
|---|---|---|
| The repository's front page, the runbook and the probe reference describe 1.9.0rc4 and probe 1.7.3; their 1.8.0rc5 texts stay at their tags | `README.md`, `review/ACCEPTANCE_RUNBOOK.md`, `review/SHARED_CLASSIC_PROBE.md` | this delivery |
| A note at the top of the 1.8.0rc5 report points to the 1.9.0 report for the current state; the report itself is unchanged | `review/TECHNICAL_REPORT.md` (line 1-3 only) | M11 |
| The acceptance matrix has two new columns, `status_1.9.0rc4` and `evidence_1.9.0rc4`; the 1.8.0rc5 columns are unchanged | `review/ACCEPTANCE_MATRIX.csv` | M11 |
| **M43:** the first-page parallel proof of 1.7.0 does not close full-pipeline partition concurrency; 1.9's lanes are tested offline, two lanes passed G13 live on 1.9.0rc4 (S5b2), and the gain of a second lane is not measured | matrix `M43` (1.9 column), report 1.9.0 §10 | M11 |
| **M42:** the Azure test-VM evidence of 1.7.0rc2 does not cover 1.9.0rc4 or the client's VM | matrix `M42`, report 1.9.0 §12 | M11 |
| **M26:** the "live In Store example" wording does not override the target, Vernon Hills **PICKUP** | matrix `M26` | M11 |
| **B29:** verified source links do not prove product-page access; stage O1 measured it (1 of 14 product pages rendered), S1b again (2 of 8) | matrix `B29`, report 1.9.0 §6 | M11 |
| Page 2 is implemented; four digital descriptions exist in Q2 but their terms were incomplete; the six Q2 category labels are rows 22-27, not all 28 CSV rows; Lakeshore East's counts are not proof for Vernon Hills | report 1.9.0 §1, §6, §7, §13 | M11 |
| The cost report gains a section 0 for 1.9 (the shared trial ledger, the stages of 2026-11-06 and 2026-11-09, latencies and the one-lane rate); sections 1 to 7 are unchanged | `review/COST_AND_RUNTIME_REPORT.md` | M8, M9 |
| The brand readings of 1.8.0rc5 and 1.9 rely on filters that only a form-A answer of the site carries; what the 1.8.0rc5 report says about reading above-window listings by brand holds for form-A answers only (every answer of 2026-11-02 was form A, 50 of 203 on 2026-11-09) | report 1.9.0 §3.2, §13 | the paging census of 2026-11-09 |
| The outcome closed in the shared ledger for stage S3b (2026-11-09 16:14Z) said the brand list "is no longer in the page the collector reads" and that a second run "would meet the same page state"; the census made afterwards found the list in 50 answers of that day. Corrected in the report; the closed ledger outcome is part of the hash chain and is not amended | report 1.9.0 §4 | the paging census of 2026-11-09 |

**The Casablanca offset of 2026-11-02 was checked and is not changed.** The 1.8.0rc5 report says "Africa/Casablanca is
UTC+0 on this date"; the 1.9 brief asked for it to be corrected to UTC+1. It is UTC+0: Morocco left GMT+1 and returned
to GMT on 2026-09-20 ([timeanddate](https://www.timeanddate.com/news/time/morocco-abolish-dst.html),
[Microsoft's time-zone guidance for Morocco 2026](https://techcommunity.microsoft.com/blog/dstblog/interim-guidance-for-morocco-dst-change-2026/4551672),
[Wikipedia](https://en.wikipedia.org/wiki/Daylight_saving_time_in_Morocco)). The IANA time-zone database 2026e
(Python `tzdata` 2026.5) gives +01:00 on 2026-09-19 and +00:00 from 2026-09-21, so +00:00 on 2026-11-02:

```
python3 -c "from zoneinfo import ZoneInfo; from datetime import datetime; print(datetime(2026,11,2,12,tzinfo=ZoneInfo('Africa/Casablanca')).utcoffset())"
```

prints `0:00:00` with tzdata 2026e or later; Windows' own "Morocco Standard Time" agrees. An older time-zone database
that predates the change gives +01:00. New dates in the 1.9 documents are in UTC; the store's zone, America/Chicago,
is UTC−6 from 2026-11-01.

## Release 1.8.0rc5 (2026-11-02)

The delivered documents are published with the corrections below; the exact text of each one, before and after, is
in [`DOC_CORRECTIONS.json`](DOC_CORRECTIONS.json) (37 edits). Historical evidence (logs, run tables, the
test plan) is not rewritten: its only changes are the redactions in [`REDACTIONS.csv`](REDACTIONS.csv). Every file's
original and published SHA-256 are in [`FILE_MAP.csv`](FILE_MAP.csv).

| Correction | Where | Basis |
|---|---|---|
| **Brand partitioning** is described as implemented (`brand_partitions()` in `collection/pagination.py`, called by `read_listing`, on by default since 1.8.0rc1) and tested offline, with no live proof of complete coverage. It had been described as not implemented | `review/TECHNICAL_REPORT.md` §3, §5, §15, §16; `review/COST_AND_RUNTIME_REPORT.md` §5 (scenario A is now "without brand partitions", and B "the path 1.8.0rc5 takes") and §7; `review/PROVIDER_COMPARISON.md` §3; `review/CORRECTION_MAP.csv` C01; `review/ACCEPTANCE_MATRIX.csv` M09, B07; `evidence/census/FULL_SCOPE_ESTIMATE.json` (key `scenario_A_as_implemented` renamed `scenario_A_without_brand_partitions`, and its note) | `source/src/marianos_headless/collection/pagination.py`, `collection/oxylabs_live.py`; test `test_a_leaf_above_the_window_is_read_through_the_sites_own_brand_filter`; no Q1c or Q2 listing was above the window. `evidence/tools/census_estimate180.py`, which produced the estimate, is unchanged and still writes the old key |
| **Recovery:** "without a page fetched twice" is replaced. No completed page was fetched again; the page in flight at each stop was requested again, and failed requests were retried | `review/COST_AND_RUNTIME_REPORT.md` §4; `review/TECHNICAL_REPORT.md` §10 (a bullet added); `review/ACCEPTANCE_RUNBOOK.md` §6 | `evidence/accounting/REQUEST_LEDGER.csv`: in flight at the stops, `interrupted_unknown` and then requested again (Q1c Candles page 3; Q2 Dog Food page 5 and School Office page 5); Q2 Hardware page 2, seven free HTTP 500 answers and then a completed page |
| **Digital coupon:** "so the site stopped showing it. This is not a collector defect" is replaced. The two captures came through the provider, and they do not show whether the retailer, the provider or something between them changed the response | `review/TECHNICAL_REPORT.md` §6 | `data/Q2-1.8.0rc4/DIGITAL_OFFER_CHANGES_Q1C_Q2.csv` |
| **Remaining work** is separated into the developer's work and the access or decisions needed from the client. A `next_owner` column is added | `review/TECHNICAL_REPORT.md` §2, §16; `review/ACCEPTANCE_MATRIX.csv` (new column); `review/ACCEPTANCE_RUNBOOK.md` §9 | the open items of the delivered report, unchanged in substance |
| **Public repository:** the client VM's address, user and host-key fingerprint, the developer's VM name, a key fingerprint and the name of a client-message draft are removed | `review/TECHNICAL_REPORT.md` §12; `review/COST_AND_RUNTIME_REPORT.md` §1; `review/ACCEPTANCE_MATRIX.csv` (8 rows, B43); `review/ACCEPTANCE_RUNBOOK.md` §0, §2 | not needed to verify any claim |
| **Classic probe test count:** "93 passed, 2 skipped" now says it is read from the log's progress marks, because the log has no pytest summary line | `classic-probe/CLASSIC_PROBE.md` | `evidence/classic-probe/from-1.8.0rc5-archive/probe_x19.log` (93 `.`, 2 `s`, exit 0) |
| **Publication layout:** references to the archives, the delivery index, the PDF summary and workstation paths or utilities point to this repository | `review/TECHNICAL_REPORT.md` §1, §10, §12, §14, §15, §17; `classic-probe/CLASSIC_PROBE.md`; `review/ACCEPTANCE_MATRIX.csv` B37, B38, B44, M54; `review/ACCEPTANCE_RUNBOOK.md` (rewritten for the repository) | [`PUBLICATION.json`](PUBLICATION.json), [`EXCLUDED.csv`](EXCLUDED.csv) |

**Kept as delivered:** the price-conflict attribution (`review/TECHNICAL_REPORT.md` §8) already says that the pages do
not establish whether the retailer, the provider or another component causes the one-cent pattern, so it is not
changed.

## Path changes

380 references in 7 documents were rewritten to repository paths: `E:<path>` (the evidence
archive) to its path under `evidence/` or `data/`, `S:<path>` (the source archive) to `source/` or `classic-probe/`, and
bare delivery file names to their paths. They are links in Markdown and plain paths in CSV. References written `D170:`
or `D150:` (the earlier 1.7.0rc2 and 1.5.0 deliveries) are kept as written. Each rewritten reference is listed in
`DOC_CORRECTIONS.json`.

| Document | References rewritten |
|---|---|
| `classic-probe/CLASSIC_PROBE.md` | 10 |
| `review/ACCEPTANCE_MATRIX.csv` | 225 |
| `review/ACCEPTANCE_RUNBOOK.md` | 15 |
| `review/CORRECTION_MAP.csv` | 50 |
| `review/COST_AND_RUNTIME_REPORT.md` | 6 |
| `review/PROVIDER_COMPARISON.md` | 9 |
| `review/TECHNICAL_REPORT.md` | 65 |

The folders moved as follows: the source archive's `source/` to `source/` and `classic_probe/` to `classic-probe/`;
the evidence archive's `runs/<run id>/` to `evidence/live-runs/<run>_<release>_<run id>/`; the delivery's tables to
`data/Q2-1.8.0rc4/`, `evidence/accounting/` and `evidence/census/`; and the review documents to `review/`.
[`FILE_MAP.csv`](FILE_MAP.csv) has every file.
