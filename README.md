# Mariano's collector 1.9.0rc4: correction delivery for review

This is a correction delivery for the client's review: **corrections verified; named milestones still pending**. It is
not a final release, it has not been accepted, and nothing here runs in production.

**Target:** Mariano's Vernon Hills, store 53100502 (1720 N Milwaukee Ave, Vernon Hills, IL 60061), **PICKUP**.

## Status on 2026-11-09

- **Collector 1.9.0rc4** is in [`source/`](source/): the exact tree of its development commit, verified offline on
  that tree (unit 488 passed; integration with PostgreSQL 183 passed (the full suite against PostgreSQL, 32 min 41 s); lint, format and types clean). The correction diff
  since 1.8.0rc5 is `git diff review-1.8.0rc5-probe171-20261105 review-1.9.0rc4-20261109 -- source`.
- **What 1.9 corrects** ([technical report](review/TECHNICAL_REPORT_1.9.0.md), [correction map](review/CORRECTION_MAP_1.9.0.csv)):
  - brand readings keep their full identity and count only pages that state their own filter (M1, M2);
  - the two price-per-measure examples are traced to their source: both are values the site displayed, now flagged (M3);
  - complete coupon terms are read from the product's own page when the provider renders it (M4: one of the four
    examples complete);
  - Mariano's changed its product tile on 2026-11-06; 1.9.0rc2 reads the new tile, and 1.9.0rc3 reports a tile's
    coupon as unknown, because tiles do not show coupons;
  - the export shows each segment's end (T06), a pause is named by its cause (T07), and the shared Classic probe
    1.7.3 refuses an unusable replay input in one line (T05);
  - listing lanes, the account-wide spending gate and the schedule's real capacity (M8); **1.9.0rc4** corrects a
    two-lane defect found live: a page is written to the database only once its answer is processed.
- **Live on 2026-11-09** (Hamza's trial account, within his approval of 295 submissions / USD 0.4425; 248
  used): ten stages, five on 1.9.0rc3 and five on 1.9.0rc4. On the final revision, **S4c read 700 distinct fresh valid products in
  one logical run**, each verified against its page; the run is rejected for coverage. Interruption, overlap refusal,
  kill and resume passed on 1.9.0rc4 with two lanes (S5b2), with no completed page asked again.
- **One site finding blocks full coverage now:** on 2026-11-09 a listing answer came in one of two forms. Form A
  (Q2's form on 2026-11-02, 50 of the day's 203 answers listing products) carries the listing's filters (brands,
  child listings), and its later pages are distinct. Form B carries no filters, and its page 2 and later list
  page 1's products: the collector counts no such page and leaves the listing incomplete, and without filters a
  listing above the 250-result window cannot be split. No above-window union has been qualified. A bounded re-ask
  of form-B answers is a proposed change with its own review (report §3.2, §15).
- **Last full live run** is still Q2 (1.8.0rc4, 2026-11-02): **1,137 fresh valid**, 1,160 retained, historically
  **rejected**; unchanged. The full category scope is **not completed**; the exact queue is
  [`INCOMPLETE_QUEUE_190.csv`](evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv).
- **Not done, waiting on others:** the client's VM checks (the VM is deallocated; at the client's request no SSH
  attempt was made); the full category scope (beyond the trial credit); the schedule (off); Classic (disabled, not
  approved); support and IP terms.

## Contents

| Path | What it holds |
|---|---|
| [`source/`](source/) | Collector 1.9.0rc4 ([setup](source/README.md), [CLI](source/docs/CLI.md), [operations](source/docs/OPERATIONS.md), [Azure](source/docs/AZURE.md)) |
| [`classic-probe-1.7.3/`](classic-probe-1.7.3/) | The shared Classic probe 1.7.3, live mode disabled: C1 to C5 and T05 corrected ([pinned reference](review/SHARED_CLASSIC_PROBE.md)) |
| [`classic-probe/`](classic-probe/) | The frozen probe 1.6.0 of 1.8.0rc5, kept for reference ([note](classic-probe/CLASSIC_PROBE.md)) |
| [`review/`](review/) | [Technical report 1.9.0](review/TECHNICAL_REPORT_1.9.0.md), [correction map 1.9.0](review/CORRECTION_MAP_1.9.0.csv), [acceptance matrix](review/ACCEPTANCE_MATRIX.csv) (1.9 columns beside 1.8.0rc5's), [the 29 earlier audit items](review/AUDIT_29_RECONCILIATION.csv), [runbook](review/ACCEPTANCE_RUNBOOK.md), [cost and runtime](review/COST_AND_RUNTIME_REPORT.md), [provider comparison](review/PROVIDER_COMPARISON.md); the 1.8.0rc5 [report](review/TECHNICAL_REPORT.md) and [map](review/CORRECTION_MAP.csv) as published |
| [`data/Q2-1.8.0rc4/`](data/Q2-1.8.0rc4/) | The Q2 dataset, its coverage and page tables ([description](data/Q2-1.8.0rc4/README.md)) |
| [`evidence/`](evidence/) | [1.9 evidence](evidence/1.9.0/README.md) (live stages, paging census, queue, reproductions, tests, ledger); the live runs, probes, tests, census, ledger and tools of 1.8 ([index](evidence/README.md)) |
| [`walkthrough/`](walkthrough/) | Three recorded walkthroughs of 1.8: rc4 live and rc5 offline ([description](walkthrough/README.md)) |
| [`manifests/`](manifests/) | Checksums, file map, corrections, redactions, exclusions and the publication record |

## Verify (offline, no request sent)

```
git clone https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper
git checkout review-1.9.0rc4-20261109
sha256sum -c manifests/SHA256SUMS.txt
python3 manifests/check_frozen_trees.py          # source/, classic-probe-1.7.3/ and classic-probe/ as published
git rev-parse HEAD:source HEAD:classic-probe-1.7.3   # 7a4dfa05 and 912801d0: the development trees
python3 evidence/tools/check_records.py data/Q2-1.8.0rc4/products_fresh.json evidence/live-runs/Q2_1.8.0rc4_01M6E5V6CASQ8F00VC8PE9TFYW 10 1
cd source && uv sync --frozen && uv run pytest -q tests/unit
```

The full sequence, including the integration suite, the probe, Docker and the client's VM, is in the
[acceptance runbook](review/ACCEPTANCE_RUNBOOK.md).

## Remaining work

[Technical report 1.9.0 §15](review/TECHNICAL_REPORT_1.9.0.md#15-open-items-the-smallest-next-live-proposal-and-milestones)
gives the proposed change and its contingency, the next live stages with their ceilings and the dated milestones, separating
Hamza's work from the access and decisions needed from the client.
[`manifests/DOC_CORRECTIONS.md`](manifests/DOC_CORRECTIONS.md) lists the documentation corrections, including the
Casablanca offset of 2026-11-02, checked and kept at UTC+0.
