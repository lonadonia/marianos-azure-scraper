# Documentation corrections for this publication

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
