# Mariano's collector 1.10.0rc3: offline candidate for review

This is an **offline candidate** for the client's review: change C1 implemented and proved offline; no live result
yet; named milestones still pending. It is not a final release, it has not been accepted, and nothing here runs in
production.

**Target:** Mariano's Vernon Hills, store 53100502 (1720 N Milwaukee Ave, Vernon Hills, IL 60061), **PICKUP**.

## Status on 2026-11-12

- **Collector 1.10.0rc3** is in [`source/`](source/): the exact tree of its development commit, verified offline on
  that tree (unit 494 passed; integration with PostgreSQL 218 passed; lint, format and types clean). Everything since
  1.9.0rc4 is `git diff review-1.9.0rc4-20261109 review-1.10.0rc3-20261112 -- source`
  ([`TECHNICAL_REPORT_1.10.0.md`](review/TECHNICAL_REPORT_1.10.0.md)).
- **C1, in one change.** A later page answered with the products of earlier pages, and the first page of a listing
  above the 250-result window answered without the filters needed to subdivide it, are set aside; the run's other
  listings go first; the very same request (address, page, listing, filter, store, fulfillment) is asked again at
  least five minutes later, at most twice more in the run. The ceiling holds across lanes, restarts and transport
  retries, every re-ask is reserved at its worst case before it is sent, and every answer is recorded, the first one
  included. A repeat counts nothing; spent re-asks leave the listing incomplete with its reason, never complete.
- **Proved offline only.** The same 28 tests ran on 1.9.0rc4 and on the candidate: their 7 controls pass on both,
  and the 21 cases of what C1 adds fail on 1.9.0rc4 and pass on 1.10.0rc3. Four tests use answers the collector
  saved on 2026-11-09 (two C1 cases replay them through the collector); the others use synthetic pages and say so
  ([before/after](evidence/1.10.0/c1/CASES_BEFORE_AFTER.csv)).
- **A separate correction:** a complete, validated run whose automatic publication was refused ended with exit code
  0, as a success. It now ends with exit code 6 and an ERROR line; the last published dataset was never replaced,
  before or after ([before/after](evidence/1.10.0/publication_result/CASES_BEFORE_AFTER.csv)).
- **Live coverage is unchanged:** no request was sent for 1.10. As on 2026-11-09, 42 of 302 product listings are
  complete, 38 stopped at a repeated page and 222 are not collected; the Coupons route apart
  ([`INCOMPLETE_QUEUE_190.csv`](evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv)). S4c's 700 fresh valid products
  remain 1.9.0rc4's, in a run rejected for coverage. Q2 (1.8.0rc4, 2026-11-02) is still the last full live run,
  historically rejected.
- **Proposed, not approved:** the live stages S6 (later-page recovery, 130 requests, USD 0.195) and S6b (brand union
  above the window, 86 requests, USD 0.129), for a later decision by Hamza
  ([`NEXT_STAGES.json`](evidence/1.10.0/budget/NEXT_STAGES.json)). S7 and full collection are deferred.
- **Classic:** the pin stays at the shared probe 1.7.3; the Walmart project's corrected probe 1.7.4 and its Windows
  regression are linked in [`SHARED_CLASSIC_PROBE.md`](review/SHARED_CLASSIC_PROBE.md). Live Classic stays disabled.
- **Not done, waiting on others:** the client's VM checks (the VM is deallocated; nothing was attempted); the full
  category scope (beyond the trial credit); the schedule (off); Classic (disabled, not approved); support and IP
  terms.

## Contents

| Path | What it holds |
|---|---|
| [`source/`](source/) | Collector 1.10.0rc3 ([setup](source/README.md), [CLI](source/docs/CLI.md), [operations](source/docs/OPERATIONS.md), [Azure](source/docs/AZURE.md)) |
| [`classic-probe-1.7.3/`](classic-probe-1.7.3/) | The shared Classic probe 1.7.3, live mode disabled ([pinned reference](review/SHARED_CLASSIC_PROBE.md)) |
| [`classic-probe/`](classic-probe/) | The frozen probe 1.6.0 of 1.8.0rc5, kept for reference ([note](classic-probe/CLASSIC_PROBE.md)) |
| [`review/`](review/) | [Technical report 1.10.0](review/TECHNICAL_REPORT_1.10.0.md), [outstanding requirements](review/OUTSTANDING_REQUIREMENTS_1.10.0.csv), [acceptance matrix](review/ACCEPTANCE_MATRIX.csv) (1.10 columns beside the earlier ones), [the 29 earlier audit items](review/AUDIT_29_RECONCILIATION.csv), [runbook](review/ACCEPTANCE_RUNBOOK.md), [cost and runtime](review/COST_AND_RUNTIME_REPORT.md), [provider comparison](review/PROVIDER_COMPARISON.md); the 1.9.0 [report](review/TECHNICAL_REPORT_1.9.0.md) and [map](review/CORRECTION_MAP_1.9.0.csv) and the 1.8.0rc5 [report](review/TECHNICAL_REPORT.md) and [map](review/CORRECTION_MAP.csv) as published |
| [`data/Q2-1.8.0rc4/`](data/Q2-1.8.0rc4/) | The Q2 dataset, its coverage and page tables ([description](data/Q2-1.8.0rc4/README.md)) |
| [`evidence/`](evidence/) | [1.10 evidence](evidence/1.10.0/README.md) (the C1 and publication cases before and after, diffs, test sessions, the coupon check, the proposed stages, the requirements for later evidence); [1.9 evidence](evidence/1.9.0/README.md); the 1.8 evidence ([index](evidence/README.md)) |
| [`walkthrough/`](walkthrough/) | Three recorded walkthroughs of 1.8: rc4 live and rc5 offline ([description](walkthrough/README.md)) |
| [`manifests/`](manifests/) | Checksums, file map, corrections, redactions, exclusions and the publication record |

## Verify (offline, no request sent)

```
git clone https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper
git checkout review-1.10.0rc3-20261112
sha256sum -c manifests/SHA256SUMS.txt
python3 manifests/check_frozen_trees.py          # source/, classic-probe-1.7.3/ and classic-probe/ as published
git rev-parse HEAD:source HEAD:classic-probe-1.7.3   # 22ebcf96 and 912801d0: the development trees
cd source && uv sync --frozen && uv run pytest -q tests/unit
uv run pytest -q tests/integration/test_reask_c1.py tests/integration/test_publication_result.py
```

The same cases on 1.9.0rc4, the before/after tables and the full suites are in
[`evidence/1.10.0/REPRODUCE.md`](evidence/1.10.0/REPRODUCE.md); the full sequence, including the probe, Docker and
the client's VM, in the [acceptance runbook](review/ACCEPTANCE_RUNBOOK.md).

## Remaining work

[`OUTSTANDING_REQUIREMENTS_1.10.0.csv`](review/OUTSTANDING_REQUIREMENTS_1.10.0.csv) gives every open item with its
owner, what blocks it, the exact evidence that would close it and the next action;
[technical report 1.10.0 §11](review/TECHNICAL_REPORT_1.10.0.md#11-what-remains-and-who-decides) sums it up, and
[`QUALIFICATION_EVIDENCE_REQUIREMENTS.md`](evidence/1.10.0/QUALIFICATION_EVIDENCE_REQUIREMENTS.md) fixes in advance
what the later live evidence must contain. [`manifests/DOC_CORRECTIONS.md`](manifests/DOC_CORRECTIONS.md) lists the
documentation corrections.
