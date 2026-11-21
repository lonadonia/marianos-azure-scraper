# Evidence of 1.10.0rc7 (2026-11-21)

Everything in this folder is offline. Nothing here sent a request to the retailer or to any provider, and no live
run was made for 1.10.0rc7. Two evidence classes appear, and each file says which one it is:

* **fixture tests**: the collector's tests against a local mock transport or a local mock site, with a throwaway
  PostgreSQL. The proxy variables point at a closed local port, so no request can leave the workstation;
* **offline replays of pages stored live**: R7's (2026-11-17, 1.10.0rc6) and F2's (2026-11-16, 1.10.0rc5) stored
  pages, read again by `source/tools/replay_routes.py`. A replay re-reads what a live run stored and is not a new
  live observation.

| Folder | What it holds |
|---|---|
| [`reconciliation/`](reconciliation/) | One line per baseline listing for each run (`routes_R7.csv`, `routes_F2.csv`), a summary per run with its replay ID and the SHA-256 of every input, one detail file per listing (`detail/<run>/`, page by page: fetch, SHA-256, time, products, what is missing), [`MISSING_UPCS.csv`](reconciliation/MISSING_UPCS.csv) (each product listed on a counted page without a record of its run) and [`NEWLY_VERIFIED_R7_VS_F2.csv`](reconciliation/NEWLY_VERIFIED_R7_VS_F2.csv) |
| [`tests/`](tests/) | The suites on 1.10.0rc7's commit, and the focused tests before and after, with logs and JUnit files |
| [`validation/`](validation/) | `validate-export --file` on R7's and F2's four products files |
| [`accuracy/`](accuracy/) | The rechecks of section 4 of the addendum: the strict sample checks with lists read from the stored pages, the named products, the product pages' Savings documents |
| [`FILE_MAP.csv`](FILE_MAP.csv) | Every file of this folder with its SHA-256 as prepared and as published; a file in which a private identifier (a workstation name or folder) was masked says so, with the masks it holds |

## The replays

Inputs, all published except the stored pages:

* R7: `evidence/runs/R7fin_copy/` on this branch (`db_tasks.csv`, `db_listing_pages.csv`, `db_page_fetches.csv`,
  `db_runs.csv`, `export/provenance.json.gz` decompressed, `export/memberships.json`,
  `export/coverage_reconciliation.csv`);
* F2: the same files of `evidence/runs/F2d/` at the tag `review-1.10.0rc5-20261116`;
* the 1.9 baseline queue: `evidence/coverage/INCOMPLETE_QUEUE_190.csv` (302 listings and the Coupons route);
* the stored pages (`stored/<run>/live/dom/<fetch>.html.gz`), which stay private. Each one is named by its SHA-256 in
  the run's `STORED_PAGES_PRIVATE.csv` and in the detail files.

Each summary lists the SHA-256 of every input it read; they equal the published files' (the provenance after
decompression). Without the stored pages the replay still audits every listing, but it marks each page
UNVERIFIABLE (capture missing) instead of checking its hash and its products.

    cd source
    uv sync --frozen
    uv run --frozen python -I -X utf8 tools/replay_routes.py RUN_DIR ../evidence/coverage/INCOMPLETE_QUEUE_190.csv F2 OUT
    uv run --frozen python -I -X utf8 tools/replay_routes.py RUN_DIR ../evidence/coverage/INCOMPLETE_QUEUE_190.csv R7 OUT --compare F2=OUT

| Run | Replay ID | Baseline listings complete | Counted pages verified | Unverifiable |
|---|---|---|---|---|
| F2 | `RPL-F2-c0f33426c40e` | 96 (94 with products, 2 empty) | 416 | 0 |
| R7 | `RPL-R7-76c0932dbc0a` | 21 (19 with products, 2 empty) | 132 | 0 |

The replay ID is a digest of the inputs and of the tool (`tool_sha256` in each summary: `8eff4a2b…`, the file
`tools/replay_routes.py` of commit `0073277`, unchanged in `ec10cde`, whose `src/` tree `cbee0f2f` is also unchanged: the replays hold for the candidate).

Columns of `routes_<run>.csv`: the store and fulfillment; the CSV row, its category and the baseline listing; the
listing the run planned (its ID, parent, kind, filter, requested URL, subdivisions); the counted pages, the
requested pages, the listings the source returned, the pages' SHA-256 and their first and last observation times;
the total the source reported; the distinct products listed on the counted pages; the fresh records linked to the
listing; how many of them are valid, cross-listed or excluded with reasons; duplicates and sponsored placements;
the missing and unexpected products and the pages they are missing from; the zero-result evidence of an empty
listing; how many captures were verified or not; the status the listing's cursor, the published 1.10.0rc6 export
and the 1.10.0rc7 audit give it, and the final reason; the detail file and its SHA-256. UPCs are text and keep
their leading zeros.
