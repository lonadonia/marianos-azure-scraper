# Earlier deliveries

The default branch holds only the latest delivery. Every earlier delivery stays complete, unchanged, at its own
review tag (an annotated tag; none was moved or replaced):

| Tag | Commit | Date | What it delivered |
|---|---|---|---|
| [`review-1.10.0rc5-20261116`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.10.0rc5-20261116) | `76e72ab` | 2026-11-16 | collector 1.10.0rc5: the live full run F2 (stopped by a store-check defect, OR-19), its export validation killed for lack of memory (OR-20), the live publication tests P4 to P6, the pilots L1 and L2, F1 on 1.10.0rc4; not final |
| [`review-1.10.0rc3-20261112`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.10.0rc3-20261112) | `e43cce2` | 2026-11-12 | collector 1.10.0rc3: change C1 implemented and proved offline; no live result |
| [`review-1.9.0rc4-20261109`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.9.0rc4-20261109) | `039fb14` | 2026-11-09 | collector 1.9.0rc4: corrections verified live on 2026-11-09 (stages S1 to S5b2) |
| [`review-1.8.0rc5-probe171-20261105`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.8.0rc5-probe171-20261105) | `65880b4` | 2026-11-05 | pinned reference to the shared Classic probe 1.7.1 |
| [`review-1.8.0rc5-probe170-20261104`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.8.0rc5-probe170-20261104) | `54fe3a6` | 2026-11-04 | pinned reference to the corrected shared Classic probe 1.7.0 |
| [`review-1.8.0rc5-20261102`](https://github.com/lonadonia/marianos-azure-scraper/tree/review-1.8.0rc5-20261102) | `1f568b8` | 2026-11-02 | collector 1.8.0rc5: correction delivery; the Q2 run of 1.8.0rc4, the recorded walkthroughs of 1.8 |

Each folder removed from the default branch by a cleanup is listed in
[`EARLIER_DELIVERIES.csv`](EARLIER_DELIVERIES.csv) with its file count, the tag that holds it complete and its Git
tree ID there, which is the same tree the default branch held before that cleanup. The cleanup before 1.10.0rc6
removed 1.10.0rc5's `evidence/` (its live runs S6, S6b, L1, L2, P1 to P6, F1 and F2 with their exports, the
publication tests, the walkthrough and the samples), `review/` (its report, runbook, acceptance matrix, audit
reconciliation and outstanding list) and `manifests/`; they are complete at `review-1.10.0rc5-20261116`. The cleanup
before 1.10.0rc5 removed, complete at `review-1.10.0rc3-20261112`:

- `evidence/`: the evidence of 1.8 (Q1 to Q2, the census, the walkthrough frames), 1.9 (the live stages of
  2026-11-09) and 1.10.0rc3 (the offline C1 proof);
- `review/`: the technical reports of 1.8.0rc5, 1.9.0rc4 and 1.10.0rc3, their acceptance matrices, correction maps,
  runbooks, cost reports and the provider comparison, as published;
- `classic-probe-1.7.3/` and `classic-probe/`: the shared Classic probe 1.7.3 (pinned by 1.10.0rc3, live mode
  disabled) and the frozen probe 1.6.0;
- `data/`: the Q2 dataset of 1.8.0rc4 and its coverage tables;
- `walkthrough/`: the three recorded walkthroughs of 1.8 (rc4 live, rc5 offline);
- `manifests/`: their checksums, file maps, redactions and corrections.

To read one: `git checkout <tag>`, or open the link. To compare a later delivery with an earlier one:
`git diff <earlier tag> <later tag> -- source`.
