# The full-run estimate for 1.10.0rc6, and what the live runs measured

| When | Basis | A full run | USD (reservation rate) |
|---|---|---|---|
| 1.10.0rc5 ([its estimate](https://github.com/lonadonia/marianos-azure-scraper/blob/review-1.10.0rc5-20261116/evidence/estimate/ESTIMATE_1.10.0rc5.json)) | the census's 3,019 to 4,826 listing pages at F2's 1.43 submissions a completed page | 4,321 to 6,906 submissions | 6.48 to 10.36 |
| Before R6 (offline, [`ESTIMATE_1.10.0rc6.json`](ESTIMATE_1.10.0rc6.json)) | each listing's own total where a run recorded one, else the census; F2's 1.43 a page | 2,223 to 2,646 pages, 3,190 to 3,796 submissions, 3.7 to 4.4 hours with two lanes | 4.79 to 5.69 |
| After R6's first slice ([`REPROJECTION_after_R6a.json`](REPROJECTION_after_R6a.json)) | R6a's own rate at 23Z: 65 submissions for 24 counted pages (2.708 a page), 21.5 s a page | the pages left at that rate: 5,956 to 7,102 submissions | short by **4.14 to 5.86** |
| After R7's five slices ([`REPROJECTION_after_R7c.json`](REPROJECTION_after_R7c.json); one file after each slice) | R7's own rate, 03Z to 05Z: 256 submissions for 132 counted pages (1.939 a page), 24.4 s a page with two lanes | the pages left at that rate: 4,056 to 4,876 submissions, 14.2 to 17.1 hours | 6.0840 to 7.3140: short by **1.6650 to 2.8950** |
| A full run of a corrected candidate ([`FULL_RUN_AT_R7_RATE.json`](FULL_RUN_AT_R7_RATE.json)) | R7 cannot complete on 1.10.0rc6 (OR-22, OR-23): the next full run reads every page, 2,223 to 2,646 of them, at R7's rate | 4,312 to 5,132 submissions, 15.1 to 18.0 hours with two lanes | 6.4680 to 7.6980: short by **2.0490 to 3.2790** |

**The credit.** Mariano's envelope of the new credential is **USD 4.90** (cap 5.00 less 0.10 headroom), 3,266
submissions at the reservation rate. When R7 began, USD 4.7935 (3,195 submissions) was left: P7 and R6 had used the
rest (see [`../ledger/`](../ledger/README.md)).

## The site serves page 1 again

For a page 2 or later, the site's search sometimes answers with page 1's products: the request asks for page N (the
stored answer's own request variables say so) and the answer holds exactly the products of page 1, under a new search
ID. The collector judges such an answer `repeated`, counts nothing from it and asks the page again after a wait (at
most two re-asks a page, at least 300 s apart). Each repeat costs one submission, and a page whose re-asks are all
repeated stays unread, which the coverage gate (G3) reports. Every repeated answer of every run so far repeats page 1.

[`REPEATED_PAGES_BY_HOUR.csv`](REPEATED_PAGES_BY_HOUR.csv) counts, by hour (UTC) and run, the answers to a page 2 or
later judged new or repeated:

| Hour (UTC) | Chicago time | Runs | Answers | Repeated |
|---|---|---|---|---|
| 2026-11-16 03Z to 04Z | 21:00 to 22:59 (Sunday) | S6, S6b | 52 | 5 (10%) |
| 15Z | 09:00 | L1, L2 (and P1) | 106 | 26 (25%) |
| 16Z | 10:00 | F1a (and P1 to P3) | 101 | 32 (32%) |
| 17Z | 11:00 | F2 | 327 | 91 (28%) |
| 18Z | 12:00 | F2 (and P4 to P6) | 73 | 43 (59%) |
| 23Z | 17:00 | P7, R6a | 34 | 29 (85%) |
| 2026-11-17 03Z | 21:00 (Monday) | R7a, R7a2, R7b, R7w, R7c (R7) | 16 | 7 (44%) |
| 04Z | 22:00 | R7a, R7a2, R7b, R7w, R7c (R7) | 89 | 28 (31%) |
| 05Z | 23:00 | R7a, R7a2, R7b, R7w, R7c (R7) | 34 | 17 (50%) |

R6a, at 23Z, spent 2.708 submissions a counted page (F2: 1.43). At that rate the rest of a full run needed USD 8.93 to
10.65 against 4.79 left, so R6 was stopped after its first slice and finalized offline: its gates were evaluated and
its publication refused (see [`../runs/R6fin/`](../runs/R6fin/)). R7 was then started at 03Z, the hour of the lowest
share measured on 2026-11-16 (10%); at that hour on 2026-11-17 the share was 44% (R7's first slice, below), so the
hour alone does not predict it.

**R7, measured.** Over its five slices (2026-11-17, 03:00Z to 05:35Z, two lanes) R7 sent 256 submissions for 132 counted pages: 1.939 submissions and 24.4 s of execution a counted page, against F2's 1.43 and 6.02 s. The difference is the repeated pages: each costs a submission and a wait of at least 300 s before its re-ask. Of the 35 requests R7 set aside, 23 were recovered by a re-ask, 6 had both re-asks repeated and 6 were still waiting at its end ([`../operations/REASK_OUTCOMES_BY_HOUR_RC6.csv`](../operations/REASK_OUTCOMES_BY_HOUR_RC6.csv)). After each slice the rest was reprojected at R7's own rate (`REPROJECTION_after_<slice>.json`); after the last, the rest of R7 needed 4,056 to 4,876 submissions, USD 6.0840 to 7.3140, against USD 4.4200 left.

R7 itself cannot complete on 1.10.0rc6. The site's menu links Hard Cider 08194 with a malformed address, which 1.10.0rc6 asks as linked; the provider brings no page for it, and that stopped six of R7's ten executions, each about 5 minutes after its start (OR-22, OR-23; corrected on the branch `marianos-1.10-next`, not released). The next full run is therefore that of a corrected candidate, from its first page: at R7's rate, 2,223 to 2,646 pages need 4,312 to 5,132 submissions, USD 6.4680 to 7.6980, and 15.1 to 18.0 hours of execution with two lanes, short by USD 2.0490 to 3.2790 of what is left ([`FULL_RUN_AT_R7_RATE.json`](FULL_RUN_AT_R7_RATE.json), its formula inside). The rate is that of R7's hours, not a bound: the share of repeated pages changes by the hour and by the day.

## How the offline estimate was made

Every input, formula and result is in [`ESTIMATE_1.10.0rc6.json`](ESTIMATE_1.10.0rc6.json), with one row per CSV row
in [`ESTIMATE_ROWS_1.10.0rc6.csv`](ESTIMATE_ROWS_1.10.0rc6.csv). The pages a full run reads are counted per CSV row,
from each listing's own total wherever a run recorded one (F2 for rows 1 to 15; L1, L2 and S6 for rows 22 to 27), else
from the census of 2026-11-02.

**Listings with a recorded total** (rows 1 to 14 and 22 to 27):
- A listing within the window costs its pages at 24 a page.
- A listing above the window costs its page 1 plus its child listings' pages, as its page 1 named them. F2 recorded
  260 child listings of 25 listings.
- **7 of the 260 children are themselves above the window**: 311, 255, 365, 323, 275, 375 and 397 products, in
  Grocery, Breakfast and Candy. The site names no child of theirs, so the collector reads each one through the
  retailer's brand filter, one reading per brand. The rc3 report measured this on stored pages at 4.5 to 5.7 times
  a listing's plain pages (cold cereal: 68 pages against 12). These 7 leaves hold 99 plain pages, which come to 446 to
  564 pages through brands: **the largest single cost in the run.**

**Listings with no recorded total** (row 15 beyond its 3 read listings, rows 16 to 21):
- The census's pages, times 1.0 (low) or 1.041 (high). 1.041 is the ratio of bottom-up to census pages measured on
  the rows that have both.
- Plus brand readings for the share of products that rows 1 to 14 hold in leaves above the window (10.1%).
- Personal Care (row 17) has neither a census nor a run: 6 to 18 pages a listing.

**Submissions:** 1.43 a page (F2's ledger rows, unknown outcomes included, per completed listing page: its repeats and
re-asks included), plus 11 a run (3 robots.txt reads, at most 4 answers of the Coupons page, the 4 named product
pages). **Time:** 6.02 s of execution per completed page with two lanes (F2).

## What F2's traces showed, and what 1.10.0rc6 changes

| Found in F2's traces | Effect on a full run | In 1.10.0rc6 |
|---|---|---|
| A listing's subdivisions were queued behind every listing of the plan. F2 planned the subdivisions of 25 listings above the window and read none before it stopped. | No listing above the window could finish before the whole plan had been read once; a stop left all 25 incomplete. | **Changed.** Listing tasks are leased by their place in the plan, and a listing's subdivisions in the order they were found, right after it. |
| With `coverage.read_product_terms` on, every tile's product page is one more request. | About as many requests as products, roughly doubling a run. | **Changed.** `--term-upc` names the products whose pages are read (each once a run, when its card is met). R6 and R7 name the 4 product pages of the review; every other product is recorded from its card. |
| The rows that the review's traces and product pages depend on (22, 27, 15) come last in CSV order. | A run short of credit ends before them. | **Changed.** `--rows-first 22,27,23,24,25,26,15` reads those rows first. Only the order changes: the plan is the same, and the order is recorded with the run. |
| 05017 is planned under rows 2 and 12: pages 1 to 3 are read twice. | 3 pages. | Not changed (below). |
| 12 child listings of 01006, 18001 and 04003 are also listings of the plan: read once as a row's listing and once as a subdivision. | 53 pages. | Not changed (below). |

**Why the duplicates stay:** together they are 56 pages, about 2.5% of a full run. Reading a listing once for two
places in the plan would change how the coverage file reconciles each CSV row and each parent with its own pages.
That reconciliation is part of the acceptance (G3), so the duplicates are listed here rather than removed in this
candidate.

**What does not change:** completeness (every listing to its end, every subdivision reconciled against its parent's
total), store and fulfillment proof on every page, provenance (every record traced to its stored page and hash), and
the retry limits.

## Caveats

- The offline estimate applies the 1.43 rate and the 6.02 s of rows 1 to 15 to every row; the live rates above
  replace them as they are measured, and they depend on the hour.
- The brand factor is from stored pages of Breakfast, not from a live brand reading.
- USD is at the reservation rate: the highest non-AI list price (USD 1.50 per 1,000), read 2026-11-03. It is not an
  invoice, and the account's balance is not readable by API.

## Reproduce

The runs F2, L1, L2 and S6 and the census comparison are published at the 1.10.0rc5 tag; P7, R6 and R7 are here.
From a clone of this repository (tools in [`../tools/`](../tools/README.md)):

```
mkdir rc5 && git archive review-1.10.0rc5-20261116 evidence/runs evidence/estimate | tar -x -C rc5
python -I evidence/tools/listing_totals.py rc5/evidence/runs totals.json
python -I evidence/tools/estimate_rc6.py rc5/evidence/runs/F2d totals.json rc5/evidence/estimate/ROWS_F2_VS_CENSUS.csv \
    ESTIMATE_1.10.0rc6.json ESTIMATE_ROWS_1.10.0rc6.csv
python -I evidence/tools/repeats_by_hour.py REPEATED_PAGES_BY_HOUR.csv \
    rc5/evidence/runs/{S6,S6b,L1,L2,P1,P2,P3,F1a,F2a,F2b,F2c,F2d,P4,P5,P6} evidence/runs/{P7,R6a,R6fin}
python -I evidence/tools/reproject6.py evidence/estimate/ESTIMATE_1.10.0rc6.json evidence/ledger/ledger_after_R6a.json \
    evidence/runs/R6a
python -I evidence/tools/reproject6.py evidence/estimate/ESTIMATE_1.10.0rc6.json evidence/ledger/ledger_after_R7c.json \
    evidence/runs/R7a evidence/runs/R7a2 evidence/runs/R7b evidence/runs/R7w evidence/runs/R7c   # REPROJECTION_after_R7c.json
```

The two estimate files and the table are byte-identical to the ones here (checked on the workstation from the
published files of the 1.10.0rc5 tag).
