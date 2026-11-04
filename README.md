# Mariano's collector 1.8.0rc5: correction delivery for review

This is a correction delivery for the client's review. It is not a final release, and it has not been accepted.

**Target:** Mariano's Vernon Hills, store 53100502 (1720 N Milwaukee Ave, Vernon Hills, IL 60061), **PICKUP**.

## Status

- **Pagination is corrected** (client finding C01): every listing is read page by page, and each page is checked
  before its products count.
- **Q2, the last live collection run** (`01M6E5V6CASQ8F00VC8PE9TFYW`, 2026-11-02), ran release candidate **1.8.0rc4**:
  **1,137 fresh valid** products and **1,160 retained**, with no duplicate UPC or URL.
- **1.8.0rc5**, the frozen source here, has **offline verification only and no live run**. Its one change after rc4
  is how the integrity gate G13 treats a page the provider never delivered.
- **Coverage in Q2:** CSV rows 23–27 complete. Row 22 (Pet Supplies) has a one-product gap: Cat Food has 231 of 232.
  Rows 0–21 were not collected in Q2.
- **Still open:**
  - full category coverage;
  - complete digital-offer terms;
  - a live verification of the final version;
  - the client's Azure and Docker acceptance checks.
- The Classic probe's live mode **stays disabled**, and its paid test is not approved. Schedules are **off**.

## Contents

| Path | What it holds |
|---|---|
| [`source/`](source/) | Collector 1.8.0rc5: the frozen tree of commit `ee5ec99b27bf68f63f6026a5b2e97937abccc5d3` ([setup](source/README.md), [operations](source/docs/OPERATIONS.md), [Azure](source/docs/AZURE.md)) |
| [`classic-probe/`](classic-probe/) | Offline Classic probe 1.6.0, with live mode disabled ([note](classic-probe/CLASSIC_PROBE.md)). Its defects C1 to C5 are corrected in the shared probe 1.7.0: [pinned reference](review/SHARED_CLASSIC_PROBE.md) |
| [`review/`](review/) | [Technical report](review/TECHNICAL_REPORT.md), [correction map](review/CORRECTION_MAP.csv), [acceptance matrix](review/ACCEPTANCE_MATRIX.csv), [runbook](review/ACCEPTANCE_RUNBOOK.md), [cost and runtime](review/COST_AND_RUNTIME_REPORT.md), [provider comparison](review/PROVIDER_COMPARISON.md) |
| [`data/Q2-1.8.0rc4/`](data/Q2-1.8.0rc4/) | The Q2 dataset, its coverage and page tables ([description](data/Q2-1.8.0rc4/README.md)) |
| [`evidence/`](evidence/) | Live runs, probes, tests, census, ledger and tools ([index](evidence/README.md)) |
| [`walkthrough/`](walkthrough/) | Three recorded walkthroughs: rc4 live and rc5 offline ([description](walkthrough/README.md)) |
| [`manifests/`](manifests/) | Checksums, file map, corrections, redactions, exclusions and the publication record |

## Verify (offline, no request sent)

```
git clone https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper
git checkout review-1.8.0rc5-20261102
sha256sum -c manifests/SHA256SUMS.txt
python3 manifests/check_frozen_trees.py          # source/ and classic-probe/ = the frozen source archive
python3 evidence/tools/check_records.py data/Q2-1.8.0rc4/products_fresh.json evidence/live-runs/Q2_1.8.0rc4_01M6E5V6CASQ8F00VC8PE9TFYW 10 1
cd source && uv sync --frozen && uv run pytest -q tests/unit
```

The full sequence, including the integration suite, Docker and the client's VM, is in the
[acceptance runbook](review/ACCEPTANCE_RUNBOOK.md).

## Remaining work

[Technical report §16](review/TECHNICAL_REPORT.md#16-open-items-and-the-smallest-next-authorized-test) separates the
developer's remaining work from the access and decisions needed from the client. The `next_owner` column of the
[acceptance matrix](review/ACCEPTANCE_MATRIX.csv) does the same for each requirement.
[`manifests/DOC_CORRECTIONS.md`](manifests/DOC_CORRECTIONS.md) lists the documentation corrections made for this
publication.
