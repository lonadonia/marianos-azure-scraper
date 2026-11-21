# Tests of the candidate 1.10.0rc7

None of these tests sends a request to the retailer or to a provider. The integration tests drive the collector
against a local mock transport or a local mock site (the browser tests: a local Chromium), each with a throwaway
PostgreSQL (pgserver). The proxy variables point at a closed local port (`HTTP_PROXY=HTTPS_PROXY=http://127.0.0.1:9`,
`NO_PROXY=127.0.0.1,localhost`). Fixtures include byte copies of pages stored live (their origin and SHA-256 in
`source/tests/fixtures/*/SOURCES.json`). None of this is a live result.

## The whole suites on the candidate, commit `ec10cde`

Commit `ec10cde09feedf5a5bab04169e6dbadb8592b5ce`, package tree `fe89f133cf7551b6cb7a26633c445508fe0c66fd`, a
clean worktree before and after (`git_status.log`, `git_status_after.log`). Hamza's workstation: Windows 11,
Python 3.12 (uv), embedded PostgreSQL, Playwright's Chromium. 2026-11-21 21:26 to 22:16 UTC, run one step at a time
in nine consecutive chunks (`CHUNK` lines in `SUITES.jsonl`), in the foreground: a background shell had been
stopped for low memory during the first attempt (below).

| Step | Result |
|---|---|
| unit (`tests/unit`) | 533 passed |
| ruff check (src, tests, tools) | All checks passed! |
| ruff format --check | 182 files already formatted |
| mypy (src, `tools/replay_routes.py`) | Success: no issues found in 88 source files |
| C1 cases (`test_reask_c1.py`) | 30 passed |
| publication cases (`test_publication_result.py`) | 6 passed |
| whole integration suite: 31 files, one at a time, browser tests included (the two files above among them) | **260 passed, 0 failed** (42.6 min of test time) |
| route audit (`test_route_audit_rc7.py`, part of the above) | 8 passed |
| publication protocol (`test_publish.py`, part of the above) | 6 passed, with the new refusal test |
| wheel (`uv build --wheel --offline`, from the local package cache: the network is closed) | `marianos_azure_headless-1.10.0rc7-py3-none-any.whl`, Name marianos-azure-headless, Version 1.10.0rc7, SHA-256 `fe3f912daba401ff4d5359bea9841eaa3c9de585235b4da3b8ece961d7254e69` |
| `marianos-collector --version` | marianos-azure-headless 1.10.0rc7 |
| worktree after every step | clean=yes |

Files: [`suites_ec10cde/`](suites_ec10cde/): `SUITES.jsonl` (the driver's record of each step: start, end, exit code,
last line, the log's SHA-256), each step's log and JUnit file, [`SUMMARY.json`](suites_ec10cde/SUMMARY.json) (each log
checked against its recorded SHA-256, the JUnit counts), the driver [`suite.sh`](suites_ec10cde/suite.sh), and
[`publication_cases/`](suites_ec10cde/publication_cases/) (what each publication case wrote, with the collector's
version and commit). The published logs drop only the collector's own JSON event lines, which the tests capture
and which name temporary folders.

Not run for 1.10.0rc7, because nothing they cover changed (`git diff d77f306 ec10cde` touches no migration,
install script, configuration file or container file): installation from the wheel on a VM, the migrations on a
VM, backup and restore, rollback on a VM, and the Docker image. The hold also keeps the VM untouched. The
migrations are exercised by the integration suite on each throwaway database. `validate-export --run` on R7 and F2
needs their databases, which are on the held VM; `--file` ran on both runs' products files
([`../validation/`](../validation/)).

## The first candidate commit, `0073277`: 7 failures, corrected in `ec10cde`

The whole suites first ran on `0073277` ([`suites_0073277/`](suites_0073277/)). Unit 533, ruff, format, mypy, C1
30 and publication 6 passed. The integration suite ended with **259 tests, 7 failed**: 5 in `test_publish.py` and
2 in `test_recovery_and_rollback.py`, all with `PublicationRefused: coverage reconciliation failed for 1
listing(s): the run's plan has no listing`. These older tests of the publication protocol (versions, the
pointer, crash safety, rollback) publish synthetic runs created directly in the database, with exports but no
plan. 1.10.0rc7's publication reads the coverage again and refuses such a run, which carries no evidence of what
it covered. That refusal is intended, so the tests changed, not the code: commit `ec10cde`
([`patches/`](patches/), the fourth) gives their synthetic runs a plan that reconciles (`tests/integration/helpers.py`:
`reconciled_plan`, one listing read to its last page, every product observed on a store-bound page, placed under
the listing and recorded fresh), and adds a test that a run without a plan, or whose page lists one product with
no record, is refused with the pointer and `latest.json` untouched. `src/` is the same in both commits (tree
`cbee0f2f`). The wheel build of `0073277` failed because `uv build` tried to fetch its build backend through the
closed proxy; `ec10cde`'s build uses `--offline`.

That first run was interrupted. Claude Code stopped the background shell of its driver for low memory
during `test_publication_safety.py` (4 of its tests had passed, no result written; partial log
`integration_publication_safety.interrupted.log`); its processes were stopped and the remaining steps were run
by [`resume_driver.sh`](suites_0073277/resume_driver.sh) (the `INTERRUPTED` and `RESUMED` lines in `SUITES.jsonl`).
The first driver's `last_line` field is empty (a backslash of its `sed` was lost when it was written); each step's
last line, taken from its log, is in [`suites_0073277/SUMMARY.json`](suites_0073277/SUMMARY.json).

## OR-25 and OR-26: the same tests before and after

The tests are a commit of their own (`8eec040`, "tests only"), the parent of the fix `92826da`. They are unchanged
since (the same Git blobs in `8eec040` and `ec10cde`), and were run on three revisions:

* **1.10.0rc6** (`d77f306`, its `src/` unchanged, with the test files of `8eec040` added);
* **`8eec040`**, whose `src/` is that of the development head `021b23f` (1.10.0rc6 with OR-21 to OR-24; the same
  tree `cd6f9b96`);
* **1.10.0rc7** (`ec10cde`).

| Tests (unchanged) | 1.10.0rc6 (`d77f306`) | `8eec040` (code of `021b23f`) | 1.10.0rc7 (`ec10cde`) |
|---|---|---|---|
| unit: `test_route_audit_rc7.py` (16) | cannot be collected: no module `route_audit` | cannot be collected | 16 passed |
| unit: `test_contract_csv_rc7.py` (3) | **3 failed** (the CSV read as JSON: `JSONDecodeError`) | **3 failed** | 3 passed |
| integration: `test_route_audit_rc7.py` (8) | 4 passed, **4 failed** | 5 passed, **3 failed** | 8 passed |

Failing on 1.10.0rc6 and on `8eec040`: `test_rc7_a_counted_product_without_a_record_is_incomplete_everywhere_and_never_published`
(`one_product_of_61` and `page_2_whole`) and `test_rc7_publication_reads_the_coverage_again_whatever_the_recorded_checks_say`.
Failing on 1.10.0rc6 only: `test_lanes_two_lanes_in_either_order_keep_what_one_lane_keeps[product_after_other]`
(OR-24, corrected on `021b23f`).

What 1.10.0rc6 did in those tests, from their evidence ([`before_after/ev_before_rc6_d77f306/`](before_after/)) and
logs:

* `one_product_of_61`: the run was validated; its coverage file said DONE, 61 unique, gap 0; its node coverage
  said DONE with 60 of 61; G3 found nothing; and the automatic publication **exited 0 and published it as version
  2, replacing the previous good dataset**;
* `page_2_whole` (24 products of page 2 without a record, R7's shape): G3 refused the run (coverage 0.607, the run
  rejected, exit 6) while its coverage file said DONE, 61 unique, gap 0;
* the publication re-read: `publish_run` published a run whose placement had been deleted after its gates
  (pytest: `DID NOT RAISE PublicationRefused`);
* two lanes in R7's order (the named product page answered after the other lane's page): 6 products of page 2 had
  no record and the run was rejected (OR-24); in the other order they were kept;
* the controls (a complete run reconciled and published; the search route; a two-lane kill and resume) passed on
  every revision.

Files: [`before_after/`](before_after/) (`STEPS.jsonl`: each step's start, end, exit code, last line and log SHA-256;
`*_identity.log`: the commit, the `src/` tree and the test files added; the logs, the JUnit files and each side's
evidence folder; the driver `driver.sh`). On 1.10.0rc6 the two unit files first ran together, and the collection
error stopped pytest before the CSV tests (`before_rc6_d77f306_unit.log`); each file was then run on its own on
every side.

## check_sample.py --strict

[`selftest/`](selftest/): `evidence/samples/selftest_check_sample.py` on the R7 sample, once with 1.10.0rc6's
`check_sample.py` (8 of 11 cases end with the wrong exit code: an altered value, a missing expected UPC, missing
evidence and an undocumented exclusion all exit 0) and once with 1.10.0rc7's (11 of 11 right).

## The change

[`DIFF_SINCE_1.10.0rc6.patch`](DIFF_SINCE_1.10.0rc6.patch) (`git diff d77f306 ec10cde`: 24 files, +2,576 −74),
[`DIFF_SINCE_021b23f.patch`](DIFF_SINCE_021b23f.patch) (18 files, +2,179 −64),
[`COMMITS_SINCE_1.10.0rc6.txt`](COMMITS_SINCE_1.10.0rc6.txt) (13 commits), and one patch per 1.10.0rc7 commit in
[`patches/`](patches/) (4).
