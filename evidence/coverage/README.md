# Coverage against the 1.9 baseline

The 1.9 delivery listed every product listing of the client's CSV rows 1 to 27 that its stages had not completed
(`evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv` at tag `review-1.10.0rc3-20261112`): **302 listings**, of which
**42 complete** (40 with products, 2 empty), 38 stopped on the site's repeated pages and 222 not collected; the
Coupons route (row 0) lists offers, not products, and is outside the 302.

[`COVERAGE_VS_1.9_QUEUE.csv`](COVERAGE_VS_1.9_QUEUE.csv) gives, for each of the 302, its status in the full run F2
(1.10.0rc5, run `01M7JNB2HDFCNR3GHQVX8FYXX6`, one run on one revision), copied as the collector wrote it in the run's own
[`coverage_reconciliation.csv`](../runs/F2d/export/coverage_reconciliation.csv). A queue listing is matched to F2's
top-level listing of the same CSV row and taxonomy ID; nothing is inferred.

| Status in F2 | Listings | What the collector means by it |
|---|---|---|
| DONE | 92 | complete, with products |
| EMPTY | 2 | complete: the site reports 0 results |
| INCOMPLETE | 40 | read, not to its reported total |
| NOT_COLLECTED | 165 | not read to an end by the run |
| NOT_PLANNED | 3 | not among the listings F2 planned from the department pages it read: 13013 Sushi (row 4); 18003 Produce (row 10); 19007 Frozen Breakfast (row 12) |
| **Total** | **302** | the 1.9 queue's product listings |

**In one sentence:** 94 of the 302 product listings complete (92 with products, 2 empty), 40 incomplete, 165 not read to an end when the collector stopped the run (not reached, or begun and unfinished), 3 not among the listings the run planned from the department pages it read (13013 Sushi (row 4); 18003 Produce (row 10); 19007 Frozen Breakfast (row 12)); the 1.9 baseline was 42 complete.

The statuses: **DONE**, the listing's distinct products reach the total the site reported for it (for a listing above
the site's 250-result window, read through the child listings its own page names, every child DONE or EMPTY, and the
distinct products of the listing and its children reaching its reported total, never a sum of child counts);
**EMPTY**, the site reports 0 results; **INCOMPLETE**, read but not to its total (the site's repeated pages outlasted
C1's re-asks, or a child listing was incomplete); **NOT_COLLECTED**, the listing was not read to an end by this run.
F2 read the CSV rows in order and was stopped by the collector in row 15 (a defect: `STORE_NOT_VERIFIED` on a page
of the right store whose product data had not loaded,
[`../operations/STORE_STOP_F2.txt`](../operations/STORE_STOP_F2.txt)); the trial credit could not have held the
whole scope in any case (see [`../estimate/`](../estimate/README.md)).

**Rows 22 to 27 elsewhere.** Today's runs L1 (1.10.0rc4, one lane) and L2 (two lanes) read rows 22 to 27 alone; L1
completed all 17 of their listings (G3 PASS), L2 left two incomplete. They are separate runs of an earlier candidate
and are reported in their own folders ([`../runs/L1/`](../runs/L1/RUN_REPORT.md), [`../runs/L2/`](../runs/L2/)); they
are **not** added to F2's count: a run is judged on its own.

Per CSV row, F2's coverage is in [`../runs/F2d/export/coverage_by_csv_row.csv`](../runs/F2d/export/coverage_by_csv_row.csv)
and in the README's table.
