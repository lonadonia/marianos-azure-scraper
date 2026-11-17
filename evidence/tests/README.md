# Tests of the candidate 1.10.0rc6

None of these tests sends a request to the provider or to the store's site. The integration tests drive the
collector against a local mock transport. That transport serves **synthetic** pages and, in the cases named below,
**byte copies of pages the collector stored live on 2026-11-16** (`source/tests/fixtures/oxylabs_2026-11-16/`, with
their origin and SHA-256 in `SOURCES.json`). None of this is a live result.

## The whole suites, on the pinned candidate

Candidate: commit `d77f306`, Git tree `b6b5f1d3`. The source was a clean extraction of that tree, with its tree ID
checked before anything was installed.

| Where | What ran | Result |
|---|---|---|
| Hamza's VM, Ubuntu 24.04, Python 3.12, PostgreSQL 16 binaries, Chromium. 2026-11-16 22:39Z to 23:08Z ([`vm_suites_d77f306/SUITES.jsonl`](vm_suites_d77f306/SUITES.jsonl): start, end, exit code, last line and log hash of each step, one JSON record a line; its last line, `ALL_DONE`, is the driver's end marker) | unit; `ruff check`; `ruff format --check`; `mypy`; the C1 cases; the publication cases; the **whole integration suite**, browser tests included | unit **506 passed**; ruff clean (188 files formatted); mypy no issues (86 files); C1 **30 passed**; publication **6 passed**; integration **247 passed** in 27 min 44 s. Every step exit 0 |
| The workstation, Windows, Python 3.12, embedded PostgreSQL. 2026-11-16 22:38Z to 23:01Z ([`workstation_integration_d77f306.log`](workstation_integration_d77f306.log)) | the integration suite without the 29 browser tests, which need Chromium on Linux | **218 passed**, 29 deselected |

## Each correction: the same tests fail before and pass after

Logs: [`before_after/`](before_after/). Each correction's tests were committed **before** its fix (the commits
marked "tests only" in [`COMMITS_SINCE_1.10.0rc5.txt`](COMMITS_SINCE_1.10.0rc5.txt)). "Before" means those same test
files, run on the code before the fix: 1.10.0rc5 (`bc19afe`) for OR-19, OR-20, OR-04 and the run order, and `88e12e0`
for the order regression. One patch per commit is in [`patches/`](patches/); the whole difference is
[`DIFF_SINCE_1.10.0rc5.patch`](DIFF_SINCE_1.10.0rc5.patch) (41 files, +2,145 −90; binary fixtures are listed there by
name, and their bytes are in `patches/`).

| Correction | Tests | Before | After |
|---|---|---|---|
| **OR-19**: a page for the store whose product data has not loaded | `test_listing_pages.py::test_or19_*` (page 1 and page 2; bounded re-asks; three controls: another store, another fulfillment, no store proof); `test_reask_c1.py::test_or19_*` (a replay of F2's Espresso re-ask stored on 2026-11-16; a re-ask without product data kept across a restart, then completed by the last re-ask) | **5 failed**, 3 passed. The 3 controls pass: a wrong store, a wrong fulfillment or no proof still stops the run | **8 passed** |
| **OR-20**: `validate-export --run` with bounded memory | `test_validate_export_or20.py` (each stored page read before the next and every record's capture checked; a mismatch names the record, its values and the page; a page missing or altered after the run rejects the export; a control mismatch); `unit/test_source_index_or20.py` (2) | **3 failed**, 1 passed; unit **2 failed** | **4 passed**; unit 2 passed |
| **OR-04**: the Coupons verdict | `test_coupons_route_or04.py` (5: a list loaded on a later answer; a list that never loads is not read and keeps the run from complete scope; the verdict and its answers kept across a restart; a product page still loading leaves the coupon unread; a control); `unit/test_coupons_list_or04.py` (8, three on real pages stored live: loading, loaded with cards, loaded and empty) | **12 failed**, 1 passed (the control) | **13 passed** |
| **Run order and named product pages** | `test_run_order_rc6.py` (6: subdivisions before the plan's next listing; a subdivision waiting for its re-ask holds no lane; `--rows-first` keeps the plan; only the named products' pages are read; a product named by its UPC; the names narrow the setting); `unit/test_cli_rc6.py` (2) | **6 failed**; unit **2 failed** | **6 passed**; unit 2 passed |
| **Order regression**, found by the full suite on `88e12e0` and fixed by `d77f306` | `test_runner.py::test_cooperative_cancel`; `test_partitions_190.py::test_a_worker_killed_inside_one_of_two_alike_brands_resumes_that_brand_alone`; two new tests: subdivisions keep the order they were planned in, and keys without a place in the plan keep their creation order | on `88e12e0`: **4 failed**, 24 passed | **28 passed** |


## Four defects found by R7: corrected on a branch, not in 1.10.0rc6

R7 runs on one release, so these four corrections are **not in 1.10.0rc6** and have not run live. They are on the
branch `marianos-1.10-next`, made from `d77f306`: each defect's tests committed first, then its fix; one more
commit, `e4f958a`, only wraps and formats the OR-21, OR-22 and OR-23 changes so that the lint and format checks
pass again, as they do on 1.10.0rc6 (no change of behaviour). One patch per commit is in
[`next_candidate/patches/`](next_candidate/patches/) (9 commits; 7 files, +397 −10); the logs are in
[`next_candidate/`](next_candidate/). "Before" is the commit of the tests alone, which holds 1.10.0rc6's code.

| Defect | Tests | Before | After |
|---|---|---|---|
| **OR-22**: Hard Cider 08194, linked by the site's menu as `/pl/hard-cider08194`, never read by any version | `unit/test_collection.py`: the listing is asked as `/pl/hard-cider/08194` with the menu's own link kept on the node, and none of the other 296 menu links changes; only that form is rewritten (7 cases, among them the malformed links the site does serve) | on `a7423c3`: **8 failed** (1.10.0rc6 plans `https://www.marianos.com/pl/hard-cider08194?pzn=relevance`) | on `61c0a0b`: **8 passed** |
| **OR-21**: a termination signal left the lanes running while the stop closed the provider session | `test_runner.py::test_a_termination_signal_cancels_the_lanes_and_hands_their_tasks_back_unfailed` (two lanes, each task at its last attempt and waiting for the provider; the worker's task cancelled as `run_async` does on SIGTERM; then the session closes) | on `c147fe5`: **1 failed**: both tasks end `failed` (the lanes, left running once the worker was cancelled, failed their tasks for good when the session closed) | on `ea2e006`: **8 passed** (the new test and the 7 other runner tests) |
| **OR-23**: a page the provider never brings stopped the run at every resume (Hard Cider in R7: a stop in every execution, about 5 minutes after its start; with OR-22, no full-scope run of 1.10.0rc6 can complete) | `test_oxylabs_collector.py::test_or23_a_page_the_provider_still_cannot_bring_after_the_resume_leaves_its_listing_incomplete_and_the_run_goes_on` (the run stops at the page once its 3 attempts are spent, as release 1.8.0 intends; the operator resumes it; the page fails again) | on `cd2af89`: **1 failed**: the run stops at the page again (`interrupted`); the 1.8.0 test beside it passes | on `abc4718`: **2 passed**: the listing stays incomplete with the reason, the run ends, one stop in all, 12 failed submissions and none charged |
| **OR-24**: with two lanes, a page whose named product pages were being read kept none of its products, although it counted as read (R7: Dog Food 27017 page 7 and Cat Treats 27022 page 2; 44 products in no record; G3 counts both listings incomplete) | `test_lanes_or24.py`, two lanes, each product page answered only once the other lane's listing has been answered, as in R7: `test_or24_a_page_waiting_for_a_product_page_keeps_its_products_while_the_other_lane_reads` (the listing route) and `test_or24_on_the_search_route_the_waiting_page_and_its_record_are_kept_while_the_other_lane_reads` (where the page being recorded was exposed as well) | on `804747f`: **2 failed**: the waiting page's products are in no record (6 on the listing route, 4 on the search route) | on `021b23f`: **2 passed** |

The whole suites on the branch's head `021b23f`, on Hamza's VM (2026-11-17, 15:01Z to 15:32Z; nothing was installed from it), in an extraction of a `git archive` of `021b23f` whose SHA-256 and Git tree (`056a3e8c`) were checked there before anything ran ([`build_console.txt`](next_candidate/vm_suites_021b23f/build_console.txt)) and again after the suites, the folder they ran in compared file by file with a new extraction ([`tree_after_suites.txt`](next_candidate/vm_suites_021b23f/tree_after_suites.txt): all 279 files identical; the one item added is `.hypothesis`, the cache Hypothesis writes in the working folder when the property-based unit tests run, and the environment and tool caches the suites make were left out of the comparison): unit **514 passed**, `ruff check` and `ruff format --check` clean, `mypy` clean (86 files), the C1 cases 30 passed, the publication cases 6 passed and the whole integration suite **251 passed** (28 min 39 s), none failed or skipped ([`next_candidate/vm_suites_021b23f/SUITES.jsonl`](next_candidate/vm_suites_021b23f/SUITES.jsonl)). On the workstation, unit 514 passed on `021b23f` (16.3 s); a run of the integration suite there was stopped with no result when the workstation ran short of memory, and is not counted. On `abc4718`, before OR-24's tests and the formatting commit, unit 514 and integration 249 passed on the workstation (41 min 12 s); on `ea2e006`, before OR-23's test, unit 514 and integration 248 passed ([`next_candidate/suites_021b23f/`](next_candidate/suites_021b23f/), [`next_candidate/suites_abc4718/`](next_candidate/suites_abc4718/), [`next_candidate/suites_ea2e006/`](next_candidate/suites_ea2e006/)). The lint (`ruff check`, `ruff format --check`) and the strict type check (`mypy`) pass on `021b23f`, as on 1.10.0rc6; on `abc4718` the lint found 27 lines too long and 5 files not formatted, and the type check passed ([`next_candidate/lint_021b23f.log`](next_candidate/lint_021b23f.log), [`next_candidate/lint_abc4718.log`](next_candidate/lint_abc4718.log)). The canonical link `/pl/hard-cider/08194` has not been
asked live: no request is made outside a run, and R7 runs on 1.10.0rc6.

The stored pages used as fixtures are the collector's own captures of F2 and P2, copied byte for byte. Their run,
fetch ID, request time and the verdict each release gave them are in `source/tests/fixtures/oxylabs_2026-11-16/SOURCES.json`.

Six of the before/after logs were written by the Windows console in its code page (cp1252), where the one non-ASCII
character they hold, "›" in category paths such as "Breakfast › Cereal & Granola", is the byte 0x9B. They are
published converted to UTF-8 and nothing else in them changed; [`ENCODING_CONVERSIONS.csv`](ENCODING_CONVERSIONS.csv) gives each
file's SHA-256 as written and as published, and the count of characters converted.

## Reproduce (offline)

```
git checkout <this tag> && cd source && uv sync --frozen
uv run pytest -q tests/unit                                          # 506 passed
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/integration/test_validate_export_or20.py tests/integration/test_coupons_route_or04.py \
    tests/integration/test_run_order_rc6.py
uv run pytest -q tests/integration/test_listing_pages.py tests/integration/test_reask_c1.py -k or19
uv run playwright install --with-deps chromium && uv run pytest -q tests/integration     # about 28 minutes
```

To see a "before" result, reverse one fix and keep its tests. From the repository root:

```
git apply -R -p3 --directory=source evidence/tests/patches/0002-*.patch   # OR-19's fix out
cd source && uv run pytest -q tests/integration/test_listing_pages.py tests/integration/test_reask_c1.py -k or19
```

The expected result is 5 failed, 3 passed. The same works for the other corrections. Each was checked on a clean
extraction of the candidate on 2026-11-16.

| Correction | Patches to reverse, in this order |
|---|---|
| OR-20 | `0004` |
| OR-04 | `0011`, then `0006` |
| Run order | `0012`, `0011`, `0010`, then `0009`. `0011` (OR-04's coverage row) and `0010` (the README) touch the same files, so OR-04's row-0 tests fail too once they are reversed. |

Apply a patch with `git apply -R -p3 --directory=source evidence/tests/patches/<number>-*.patch`, starting from a clean
checkout each time.
