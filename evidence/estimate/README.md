# The full-cycle estimate, updated with the full run F2

**Before** (`review/COST_AND_RUNTIME_REPORT.md` at tag `review-1.10.0rc3-20261112`, scenario B, all rows): a full run
of the configured scope reads **3,019 to 4,826 listing pages** (the census of 2026-11-02; rows 7, 9, 11, 13 and 17,
unmeasured then, as a range), at 1.3 submissions per counted page plus 3 per run: **3,928 to 6,277 submissions, USD
5.89 to 9.41 a run**, 48.4 to 77.3 hours with one worker at 57.7 s a page (rendered pages, 1.8), about USD 51 to 82 a
month twice weekly (8.67 runs a month).

**Measured in F2** (1.10.0rc5, one run in four slices, two lanes, unrendered listing pages, C1 on): every submission
of the run counted from the ledger, unknown outcomes included, against the listing pages the run completed (the
completed answers of its listing-page log).

| Measure | Value |
|---|---|
| Submissions (ledger rows of the four slices, unknown outcomes included) | 595 |
| Listing pages completed | 416 |
| Submissions per completed page | **1.430** (1.3 before) |
| Execution time of the slices | 0.70 h |
| Execution seconds per completed page, two lanes | **6.0** (57.7 rendered, one worker, before) |

**Updated estimate** (the page range kept, F2's measures in place of 1.3 submissions and 57.7 s a page):

| Per run | Submissions | USD (reservation rate) | Hours, two lanes | USD a month, twice weekly |
|---|---|---|---|---|
| Scenario B, all rows (3,019 to 4,826 pages) | 4,321 to 6,906 | 6.48 to 10.36 | 5.0 to 8.1 | 56.2 to 89.8 |

**The shortfall.** To complete one full run beyond what F2 read: 3,726 to 6,311 more submissions, USD 5.59 to 9.47 at the reservation rate. Mariano's could spend USD 0.3120 more of its trial envelope at the end of this delivery. A full run and its protected publication need the store-check correction (OR-19), then a funded provider account (and, for the client's acceptance, the client's environment): a decision for Hamza and the client, recorded in "What remains"

**What the census does not settle.** [`ROWS_F2_VS_CENSUS.csv`](ROWS_F2_VS_CENSUS.csv) sets, per CSV row, the census of
2026-11-02 (products listed, pages, rows not measured then) beside what F2 read (its listings' reported totals, pages
completed, distinct products, status). F2 read pages of rows 1 to 15 (1 of them completely: Floral) and none of rows 16 to 27, so it does not replace the census: the estimate keeps the census's page range and replaces only the measures per page. For the rows the census could not measure, F2's listings report Grocery 5,981; Frozen 2,559; Beverages 3,154; Coffee 777 results (the sum of the reported totals of the listings F2 reached in the row, not de-duplicated across listings); these are recorded, not used as a page count.

**Caveats.** F2 read the rows in order and was stopped by the collector in row 15, so its rates of repeated,
malformed and re-asked answers are those of the rows it read, applied to every row. The time per page is execution time over
completed pages, C1's waits included. USD is at the reservation rate (a list price read 2026-11-03), not an invoice.
Every input, formula and result is in [`ESTIMATE_1.10.0rc5.json`](ESTIMATE_1.10.0rc5.json).

**Scheduling** stays off: the brief allows a schedule only after a protected full publication, and no full run has
been published (F2 was stopped by the collector before the full scope, and its publication was refused). See "What remains" in the [README](../../README.md).
