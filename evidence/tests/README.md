# Tests of the candidate

All of this ran on Hamza's own Azure test VM (Ubuntu 24.04, Python 3.12, PostgreSQL 16 server binaries for the test
databases) on 2026-11-16, on a clean extraction of the pinned development tree whose Git tree ID was checked before
anything was installed. Nothing here sends a request to the provider or to the store's site: the integration tests
drive the collector against a local mock transport that serves **synthetic** pages (and, in four C1 tests, answers
the collector saved on 2026-11-09, replayed). None of it is a live result.

## 1.10.0rc5 (commit `bc19afe`, tree `3f456703`): the final candidate

| Folder or file | What it holds | Result |
|---|---|---|
| [`candidate_suites/`](candidate_suites/) | The whole suites, one after the other ([`SUITES.jsonl`](candidate_suites/SUITES.jsonl): start, end, exit code, last line and log hash of each) | unit 494 passed; `ruff check` and `ruff format --check` clean (181 files); `mypy` clean (86 source files); the C1 cases 28 passed; the publication-result cases 6 passed; the whole integration suite 222 passed in 25 min 46 s, none skipped; all exit 0, 16:36:18 to 17:04:09 UTC |
| [`rc5_fix/`](rc5_fix/) | The one collector change of 1.10.0rc5, pinned: the tests alone ([`1_TESTS_ONLY_570ff7c_to_a1385f8.patch`](rc5_fix/1_TESTS_ONLY_570ff7c_to_a1385f8.patch)), the fix alone ([`2_FIX_a1385f8_to_bc19afe.patch`](rc5_fix/2_FIX_a1385f8_to_bc19afe.patch)), both together ([`RC4_TO_RC5_570ff7c_to_bc19afe.patch`](rc5_fix/RC4_TO_RC5_570ff7c_to_bc19afe.patch)), and the before/after sessions ([`logs/`](rc5_fix/logs/)) | **before** (1.10.0rc4's collector with the new tests, tree `ddbb7b8e`): 2 failed, 2 passed; **after** (1.10.0rc5): 4 passed; the whole file after: 33 passed |
| [`old_new/`](old_new/) | The C1 cases and the publication-result cases run on **1.9.0rc4** (`8abc2c1`, an unchanged extraction of its collector tree with only the candidate's test files and fixtures added: [`overlay.log`](old_new/overlay.log) gives each file's hash on both sides), and one row per test with its outcome before and after | C1: 21 failed and 7 passed on 1.9.0rc4, 28 passed on the candidate ([table](old_new/C1_CASES_BEFORE_AFTER_rc5.csv)); publication result: 3 failed and 3 passed on 1.9.0rc4, 6 passed on the candidate ([table](old_new/PUBLICATION_CASES_BEFORE_AFTER_rc5.csv)); every row as expected (a new behaviour fails before and passes after; a control passes on both) |
| [`COMMITS_SINCE_1.10.0rc3.txt`](COMMITS_SINCE_1.10.0rc3.txt), [`DIFF_SINCE_1.10.0rc3.patch`](DIFF_SINCE_1.10.0rc3.patch) | The seven development commits since 1.10.0rc3 (`a1040f7`) and their whole difference in the collector's folder | the same difference as `git diff review-1.10.0rc3-20261112 <this tag> -- source` |

### What the 1.10.0rc5 fix is, and how its tests show it

The full run of 1.10.0rc4 (stage F1, [`../runs/F1a/`](../runs/F1a/)) was stopped by the collector itself with
`STORE_NOT_VERIFIED`: one listing page came back before its search had been made (no request, still loading, no
response, no product, no product card), and the store check that reads the store out of the page's own search
request failed on a request that did not exist, although the page's header and state named the right store and
fulfillment. A page like that proves nothing about another store; it is simply not an answer yet.

In 1.10.0rc5 that one check is "not applicable" when, and only when, the page holds no search request at all, is
not loaded, states no total and shows no product and no card. The page is then judged like any other unfinished
answer (malformed) and asked again within the existing retry limits. Every other store check is unchanged, and so
is the stop.

- `test_a_page_brought_before_its_search_was_made_is_asked_again_and_the_run_goes_on` (page 1 and page 2): **fails
  before** (the page is asked once and the run stops with `STORE_NOT_VERIFIED`, visible in
  [`logs/before.log`](rc5_fix/logs/before.log)) and **passes after** (asked twice, the run goes on, 60 products,
  the listing complete).
- `test_a_page_without_its_search_that_shows_products_or_another_store_still_stops_the_run` (two cases): a page
  without its search that nevertheless shows products, or that sits in another store's context, **still stops the
  run** with `STORE_NOT_VERIFIED`. These two pass before and after: the fix does not loosen the check.

## 1.10.0rc4 (commit `570ff7c`): the candidate the first live stages ran on

[`1.10.0rc4/`](1.10.0rc4/) keeps its records unchanged: its suites
([`candidate_suites/`](1.10.0rc4/candidate_suites/): unit 494, C1 28, publication 6, integration 218 passed), the
same before/after on 1.9.0rc4 ([`old_new/`](1.10.0rc4/old_new/)), the three test-only corrections made while
qualifying it on Linux, each with its patch and its before/after ([`fixes/`](1.10.0rc4/fixes/): a fixture compared
byte for byte across gzip implementations; the test browser's sandbox on Ubuntu 24.04; a scheduled-run test that
read the real clock), and the lint failure of its first commit, kept as it happened
([`rc4_first_commit_lint/`](1.10.0rc4/rc4_first_commit_lint/)). 1.10.0rc4's collector code is 1.10.0rc3's.

## Reproduce (offline)

```
git checkout <this tag> && cd source && uv sync --frozen
uv run pytest -q tests/unit
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/integration/test_reask_c1.py tests/integration/test_publication_result.py
uv run pytest -q tests/integration/test_listing_pages.py -k "before_its_search_was_made or without_its_search"
uv run playwright install --with-deps chromium && uv run pytest -q tests/integration     # about 26 minutes
```

The "before" side of the fix, from the repository root: take the fix out again with
`git apply -R -p3 --directory=source evidence/tests/rc5_fix/2_FIX_a1385f8_to_bc19afe.patch` (the new tests stay),
then run the last selection again in `source/`: 2 failed, 2 passed.
