# Mariano's collector 1.10.0rc7: delivery for review (2026-11-21)

Prepared by Hamza. Store: Mariano's Vernon Hills, location **53100502** (ZIP 60061), **PICKUP**. Times are UTC.

**Status: NOT FINAL. Offline corrections verified. Full live coverage and fresh parallel-page verification
pending.** 1.10.0rc7 corrects the defect Darren's review of 20 November found in R7's coverage file (OR-25): a
listing's verdict now comes from the products actually accounted for, and every consumer reads it. It also releases
the four corrections R7 led to (OR-21 to OR-24). Each correction has tests that fail on the code before it and pass
on 1.10.0rc7.

No request has been sent to the retailer or to any provider since 2026-11-17: Darren renewed the hold on 19 and 20
November. No money was spent, no schedule was enabled, and neither Azure VM, SSH key, run, ledger nor timer was
touched. Every result here comes from local tests on fixtures, with network access blocked, or from offline
replays of pages stored by earlier live runs. **New live listings verified since 17 November: zero.** A fresh live
verification needs Darren's separate decision; the proposal is in [section 7](#7-what-remains).

This page is the one entry point. The new interpretation is in
[`review/ADDENDUM_20261121.md`](review/ADDENDUM_20261121.md). Everything 1.10.0rc6 published stays here byte for
byte: its report [`review/REPORT.md`](review/REPORT.md), its evidence, exports, hashes, coverage tables and
publication refusals. Its entry page is kept as
[`README_1.10.0rc6_20261117.md`](README_1.10.0rc6_20261117.md), and the whole of it is at its tag.

## 1. The candidate

| | |
|---|---|
| Collector | **1.10.0rc7**, in [`source/`](source/): development commit `ec10cde09feedf5a5bab04169e6dbadb8592b5ce`, package tree `fe89f133cf7551b6cb7a26633c445508fe0c66fd`, published with the same one change as before: the test VM's host masked in `source/docs/AZURE_VM.md` ([`manifests/REDACTIONS.csv`](manifests/REDACTIONS.csv)). Check: `python3 manifests/check_source_tree.py` |
| Identity | `pyproject.toml`, `marianos_headless.__version__`, the wheel's metadata and `marianos-collector --version` all name 1.10.0rc7; every run records the release, the commit and the parser version 1.10.0 (the release series, by its documented rule) |
| This delivery | the tag `review-1.10.0rc7-20261121` (annotated). `review-1.10.0rc6-20261117` (`6906408`), `review-1.10.0rc5-20261116` (`76e72ab`) and every earlier tag are unchanged ([`EARLIER_DELIVERIES.md`](EARLIER_DELIVERIES.md)) |
| Change since 1.10.0rc6 | 13 development commits: the 9 of OR-21 to OR-24, published with 1.10.0rc6 as patches, and 4 for 1.10.0rc7 (the tests, then the fix, then version and notes, then the publication tests' fixture, after the whole suite on the third found 7 failures; see section 3) ([`COMMITS_SINCE_1.10.0rc6.txt`](evidence/rc7/tests/COMMITS_SINCE_1.10.0rc6.txt)) |
| Whole difference | [`DIFF_SINCE_1.10.0rc6.patch`](evidence/rc7/tests/DIFF_SINCE_1.10.0rc6.patch) (24 files, +2,576 −74); since `021b23f`: [`DIFF_SINCE_021b23f.patch`](evidence/rc7/tests/DIFF_SINCE_021b23f.patch) (18 files, +2,179 −64). One patch per 1.10.0rc7 commit: [`evidence/rc7/tests/patches/`](evidence/rc7/tests/patches/) |

## 2. The corrections, each failing before and passing after

| | What was wrong | What 1.10.0rc7 does | Before → after |
|---|---|---|---|
| **OR-25** (Darren, 20 Nov) | R7's coverage file said Dog Food 27017 and Cat Treats 27022 were DONE, gap 0, while 44 products of their counted pages had no record. The coverage file, G3 and the publication each read a listing differently, and none of them read the records. On 1.10.0rc6, one product of 61 lost (a coverage of 0.984, above both G3 thresholds) was validated and **published**, replacing the last good dataset | A listing is DONE only when every product its counted pages list has a record of the run placed under the listing (fresh, or excluded with its stated reasons), every counted page is bound to the store, nothing unexpected is placed from its own pages, and the products accounted for reach the source's highest total. It is EMPTY only with the store's own page stating 0 results. Subdivisions complete it by their union. One verdict is read by the node coverage, the coverage files, G3, the export and the publication, and the publication reads it again: an unexplained gap refuses it with exit 6, manual or automatic, the pointer and the files untouched | the tests, unchanged since their own commit `8eec040`: on 1.10.0rc6 the route audit's 16 unit tests cannot even be collected and 4 of 8 integration tests fail (one product of 61 lost was **published**); on the head `021b23f` 3 of 8 fail; on 1.10.0rc7 all pass ([`evidence/rc7/tests/`](evidence/rc7/tests/README.md)) |
| **OR-26** | `validate-export --file products.csv` was refused (the CSV read as JSON, exit 2) | reads the CSV as text: header order, every value a string, leading zeros as written | its 3 tests fail on 1.10.0rc6 (`JSONDecodeError`) and pass on 1.10.0rc7; R7's and F2's eight products files: exit 0, no problem ([`evidence/rc7/validation/`](evidence/rc7/validation/)) |
| **OR-21** to **OR-24** | open in 1.10.0rc6 (corrected on a branch) | released: lanes cancelled and awaited at a stop; Hard Cider 08194 asked in the site's form; a page that keeps failing no longer stops every resume; each lane keeps its own page and records while a product page is read | as published with 1.10.0rc6 ([`evidence/tests/next_candidate/`](evidence/tests/next_candidate/)), and passing again on 1.10.0rc7 |
| `check_sample.py --strict` | the sample check only reported (exit 0) | the same report by default; with `--strict`, exit 1 for an altered value, a missing expected UPC or missing evidence, 2 when it cannot check, 0 only for a genuine match; documented exclusions stay apart | its self-test: 1.10.0rc6's script 8 of 11 wrong, 1.10.0rc7's 11 of 11 right |

Focused cases, all on fixtures: the Cat Food control (234 of 234); the two short R7 pages; 223 of 224; equal
counts with a substituted UPC; overlapping subdivisions; an unbound brand reading; a page of another store; a
repeated page; a changed total; carried, cross-listed, excluded and sponsored products kept apart; one lane and two
lanes in both completion orders, with a named product page waiting while the other lane advances, on the listing
and the search routes; cancellation, a provider failure and a hard kill with resume; manual and automatic
publication over a previous good dataset. Kept and tested again: the pending-fetch guard, the store and fulfillment
checks, the bounded re-asks (at most 2, at least 300 s apart, the original reason kept), the streaming export
validation, the Coupons row, the 22 ordered string fields (gupc and unit_price empty), the source's price per
measure, pack size apart from serving size, and the offer rules.

## 3. The suites on 1.10.0rc7

On commit `ec10cde`, a clean worktree, Hamza's workstation (Windows 11, Python 3.12, embedded PostgreSQL, Playwright's Chromium, network access closed), 2026-11-21 21:26 to 22:16 UTC:

| Step | Result |
|---|---|
| unit | 533 passed |
| ruff check, ruff format --check, mypy | clean (182 files formatted; no issue in 88 source files) |
| C1 re-ask cases (`test_reask_c1.py`) | 30 passed |
| publication cases (`test_publication_result.py`) | 6 passed |
| whole integration suite, 31 files one at a time, browser tests included | **260 passed, 0 failed** |
| wheel (`uv build --wheel --offline`) and `marianos-collector --version` | 1.10.0rc7 (wheel SHA-256 `fe3f912d…`) |
| worktree before and after | clean |

The first candidate commit, `0073277`, failed 7 integration tests (`test_publish.py` 5, `test_recovery_and_rollback.py` 2): those older protocol tests publish synthetic runs with no plan, which 1.10.0rc7's publication rightly refuses. `ec10cde` gives them a plan that reconciles and adds a test of the refusal; `src/` did not change. Both runs, the interruption of the first one by a low-memory stop, logs, JUnit files and drivers: [`evidence/rc7/tests/`](evidence/rc7/tests/README.md). Not run again for 1.10.0rc7, because it changes none of them: installation on a VM, backup and restore, rollback, the container. `validate-export --run` needs R7's and F2's databases, on the held VM.

Earlier counts, attributed: **Darren's own run of 1.10.0rc6's unit suite, 506 passed**, is Darren's result. The 514 unit
and 251 integration passes published with 1.10.0rc6 were on the development head `021b23f`, not on 1.10.0rc6.
1.10.0rc6 itself passed unit 506, C1 30, publication 6 and integration 247 on Hamza's VM.

## 4. Coverage, dated, read again from the stored pages

Offline replays of the two full runs against the 1.9 baseline of 302 listings: every counted page's capture was
hashed and parsed again, and every listing was audited as in section 2. Per listing:
[`evidence/rc7/reconciliation/`](evidence/rc7/reconciliation/).

| | F2, 2026-11-16, 1.10.0rc5 | R7, 2026-11-17, 1.10.0rc6 |
|---|---|---|
| Darren's recorded result (kept) | 96 of 302 | 21 of 302 |
| Complete by 1.10.0rc7's audit | **96** (94 with products, 2 empty) | **21** (19 with products, 2 empty); the 23 apparent completions of the coverage file lose Dog Food (200 of 224 accounted for; 24 missing, all on page 7) and Cat Treats (32 of 52; 20 missing, all on page 2) |
| Counted pages verified (hash and products) | 416 of 416 | 132 of 132 |
| Cat Food 27021 | not reached | 234 of 234 |
| Records | 8,118 fresh (7,678 valid) | 2,667 fresh (**2,518 valid**), **7,869 carried** apart |
| Gates and publication | stopped before its gates | G3 and G4 FAIL, G13 and G14 PASS; publication refused (exit 6) |

Against F2, **20** of R7's complete listings are new and Fresh Herbs 06122 is complete in both
([`NEWLY_VERIFIED_R7_VS_F2.csv`](evidence/rc7/reconciliation/NEWLY_VERIFIED_R7_VS_F2.csv)). That is two runs on two
revisions, not one run's coverage.

## 5. Accuracy, rechecked from the saved evidence

* The price-per-measure traces 0084024314377 (`$19.99/oz`) and 0001280052496 (`$7.99/oz`), Cutwater and The Finnish
  Long Drink are exported as the source displays them: `check_sample.py --strict`, 5 the same.
* Nutrl appears only on a refused page; the dip appears on no saved page.
* Digital terms: 0002310014848 (R7) and 0003980014995 (P8) rendered, no savings shown; 0001780014939 and
  0001780014941 unread (never rendered).
* With expected lists read from the stored pages, the strict check on the published R7 sample passes Cat Food
  (234/234) and fails Dog Food (24 missing) and Cat Treats (20 missing), exit 1.

Details: [`evidence/rc7/accuracy/`](evidence/rc7/accuracy/) and the addendum, section 4.

## 6. Files

| Where | What |
|---|---|
| [`review/ADDENDUM_20261121.md`](review/ADDENDUM_20261121.md) | the new interpretation, dated |
| [`review/ACCEPTANCE_MATRIX.csv`](review/ACCEPTANCE_MATRIX.csv), [`AUDIT_29_RECONCILIATION.csv`](review/AUDIT_29_RECONCILIATION.csv), [`OUTSTANDING.csv`](review/OUTSTANDING.csv) | the 1.10.0rc7 columns added at the right of each file, every earlier column and value unchanged; OUTSTANDING gains OR-25 and OR-26 |
| [`review/ACCEPTANCE_RUNBOOK.md`](review/ACCEPTANCE_RUNBOOK.md) | the runbook, with a 1.10.0rc7 section at its end |
| [`evidence/rc7/`](evidence/rc7/README.md) | the reconciliation, the tests, the validation and the rechecks of 1.10.0rc7 |
| [`evidence/samples/`](evidence/samples/) | the record samples; `check_sample.py` (now with `--strict`) and its self-test |
| [`manifests/`](manifests/) | checksums, file map, redactions, the source tree check, the link check; 1.10.0rc6's manifests kept as published in `manifests/1.10.0rc6/` |

## 7. What remains

The table of owners, missing evidence and release conditions is in the addendum, section 7. In brief:

* **Fresh parallel-page verification** (Darren decides; Hamza runs). Proposed and not executed: one run of
  1.10.0rc7 reading only Dog Food 27017 and Cat Treats 27022 with two lanes, and the three named product pages on
  their short pages. Ceilings come from R7's saved traces: at most 45 submissions and USD 0.07 at the ledger's
  list rate (USD 0.0015, read on 3 November, not an invoice), and 30 minutes. It stops on a page not bound to the
  store, a challenge, or a ceiling, with no publication. It passes only if both listings' exact UPC sets are
  accounted for, R7's 44 lost UPCs included.
* **Full production**: one authorized run on one revision across rows 0 to 27, with no demonstration cap. Its report
  keeps apart the 500-fresh-valid qualification with G13/G14, coverage and yield (G3/G4), the publication, and
  runtime and cost. Two weeks of observation, retention and stock changes, the Azure walkthrough, support and IP
  terms and the client's sign-off keep their own prerequisites.
* Balance and runtime figures given earlier are dated estimates. Form A/B stays an observed correlation.

Final acceptance needs the outstanding evidence and Darren's decision.

## 8. Reproduce (offline)

    git clone https://github.com/lonadonia/marianos-azure-scraper && cd marianos-azure-scraper
    git checkout review-1.10.0rc7-20261121
    python3 manifests/check_source_tree.py          # source/ against its checksums and Git tree
    python3 -I manifests/check_links.py             # every repository link; no web address visited
    python3 -I evidence/samples/selftest_check_sample.py evidence/samples/R7
    python3 -I evidence/samples/check_sample.py evidence/samples/R7 --strict --expect evidence/rc7/accuracy/EXPECTED_27017_R7.txt   # exit 1: 24 missing
    cd source && uv sync --frozen
    uv run --frozen pytest -q tests/unit                                # 533 passed
    uv run --frozen pytest -q tests/integration/test_route_audit_rc7.py # 8 passed (needs no network)
    uv run --frozen marianos-collector validate-export --file ../evidence/runs/R7fin_copy/export/products.csv

The before runs, the replays and every suite's command and log: [`evidence/rc7/tests/`](evidence/rc7/tests/README.md)
and [`evidence/rc7/README.md`](evidence/rc7/README.md).
