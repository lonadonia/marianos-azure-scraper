# Reproduce the 1.10 evidence offline

Every command below runs offline: no request goes to Mariano's, to Oxylabs or to any other provider, and no key is
read. The tests start a throwaway PostgreSQL server of their own (the `pgserver` development dependency) unless
`MARIANOS_COLLECTOR_TEST_DATABASE_URL` names a disposable database; never point them at a database that holds data,
because they drop their tables.

What was run for this publication, where and with which result is in [`tests/`](tests/) (one record per session:
revision, clean tree, times, counts, exit code, log hash) and [`tests/SESSIONS.csv`](tests/SESSIONS.csv). The runs
were made on Windows 11 with CPython 3.12.10 and `uv`, in the development worktree at the candidate's commit with a
clean tree. The unit suite, the two case files and the lint checks were then run again in a clean extraction of the
candidate's tree, installed from its lock ([`tools/run_x_sessions_1100.sh`](tools/run_x_sessions_1100.sh), the
`x_` sessions), which was checked file for file against the tree before and after them
([`tests/x_tree_check.json`](tests/x_tree_check.json),
[`tests/x_tree_check_after_sessions.json`](tests/x_tree_check_after_sessions.json)).

## 1. The candidate, 1.10.0rc3

```
git clone https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper
git checkout review-1.10.0rc3-20261112
python3 manifests/check_frozen_trees.py     # source/ is the development tree 22ebcf96cdb2021347f0e0e4d7506ad4c36d2c10
cd source
uv sync --frozen
uv run marianos-collector --version          # marianos-azure-headless 1.10.0rc3
uv run ruff check && uv run ruff format --check && uv run mypy
uv run pytest -q -p no:cacheprovider tests/unit                     # 494 passed
uv run pytest -q -p no:cacheprovider tests/integration              # 218 passed
```

On Windows, as run here, the integration suite was run with `PSYCOPG_IMPL=python`, `PYTHONUTF8=1` and the folder
`.venv/Lib/site-packages/pgserver/pginstall/bin` first on `PATH`, so that the throwaway server's own programs are
found.

## 2. The same cases on 1.9.0rc4 and on the candidate

The C1 cases ([`source/tests/integration/test_reask_c1.py`](../../source/tests/integration/test_reask_c1.py)) and the
publication cases ([`source/tests/integration/test_publication_result.py`](../../source/tests/integration/test_publication_result.py))
load on 1.9.0rc4 as well. The "before" runs used an unchanged checkout of 1.9.0rc4 with only the candidate's test
files added beside it; [`c1/RC4_OVERLAY.json`](c1/RC4_OVERLAY.json) lists those 12 files with their SHA-256, each
checked byte for byte against the candidate's file.

From the root of the clone of section 1:

```
REPO=$PWD
git worktree add ../rc4 review-1.9.0rc4-20261109                   # 1.9.0rc4, beside the clone
RC4=$(cd ../rc4 && pwd)
OUT=$(cd .. && pwd)/c1100-runs
mkdir -p "$OUT/before/c1" "$OUT/before/publication" "$OUT/after/c1" "$OUT/after/publication"
cd "$RC4/source"
uv sync --frozen                                                   # 1.9.0rc4's own lock
for f in tests/c1_site.py tests/integration/test_reask_c1.py tests/integration/test_publication_result.py; do
  cp "$REPO/source/$f" "$f"
done
cp -r "$REPO/source/tests/fixtures/oxylabs_2026-11-09" tests/fixtures/
git status --short        # only the added files, untracked: no file of 1.9.0rc4 is changed
C1_EVIDENCE_DIR="$OUT/before/c1" uv run pytest -q -p no:cacheprovider tests/integration/test_reask_c1.py \
  --junitxml="$OUT/before/c1.junit.xml"                              # 21 failed, 7 passed
PUBLICATION_EVIDENCE_DIR="$OUT/before/publication" uv run pytest -q -p no:cacheprovider \
  tests/integration/test_publication_result.py --junitxml="$OUT/before/publication.junit.xml"   # 3 failed, 3 passed
```

The same two files on the candidate:

```
cd "$REPO/source"
C1_EVIDENCE_DIR="$OUT/after/c1" uv run pytest -q -p no:cacheprovider tests/integration/test_reask_c1.py \
  --junitxml="$OUT/after/c1.junit.xml"                               # 28 passed
PUBLICATION_EVIDENCE_DIR="$OUT/after/publication" uv run pytest -q -p no:cacheprovider \
  tests/integration/test_publication_result.py --junitxml="$OUT/after/publication.junit.xml"    # 6 passed
```

On 1.9.0rc4 the expected failures are the tests' own assertions, not errors: each `test_c1_...` and `test_fix_...`
fails, and each `test_control_...` passes. With `C1_EVIDENCE_DIR` or `PUBLICATION_EVIDENCE_DIR` set, each test
writes what it observed there before it checks anything, so a failing case still leaves its observation
([`c1/cases/`](c1/cases/) and [`publication_result/cases/`](publication_result/cases/) hold those of this
publication, per revision).

## 3. The before/after tables

```
cd "$REPO"
python3 -I evidence/1.10.0/tools/cases_table_1100.py "$OUT/before/c1.junit.xml" "$OUT/after/c1.junit.xml" \
  1.9.0rc4 1.10.0rc3 "$OUT/c1.csv"
#   28 tests: 7 controls, 21 new-behaviour cases; not as expected: 0; same tests in both runs: True
python3 -I evidence/1.10.0/tools/cases_table_1100.py "$OUT/before/publication.junit.xml" \
  "$OUT/after/publication.junit.xml" 1.9.0rc4 1.10.0rc3 "$OUT/publication.csv"
#   6 tests: 3 controls, 3 new-behaviour cases; not as expected: 0; same tests in both runs: True
```

The tool reads each test's own result element from the two JUnit files (never an exit code), and exits 1 when a
control does not pass on both revisions, a new case does not fail before and pass after, or the two runs do not hold
the same tests. Its output for this publication: [`c1/CASES_BEFORE_AFTER.csv`](c1/CASES_BEFORE_AFTER.csv) and
[`publication_result/CASES_BEFORE_AFTER.csv`](publication_result/CASES_BEFORE_AFTER.csv).

## 4. The diffs

```
git diff review-1.9.0rc4-20261109 review-1.10.0rc3-20261112 -- source                   # everything since 1.9.0rc4
```

[`diffs/`](diffs/) holds each commit's diff, made in the development repository, with the C1 commit split into
source, configuration and documents ([`diffs/C1_454b79d_source_config_docs.diff`](diffs/C1_454b79d_source_config_docs.diff))
and tests ([`diffs/C1_454b79d_tests.diff`](diffs/C1_454b79d_tests.diff); the seven saved pages are gzip files and
appear there as binary).

## 5. The coupon examples

[`coupons/COUPON_EVIDENCE_CHECK.json`](coupons/COUPON_EVIDENCE_CHECK.json) was made by
[`tools/coupon_check_1100.py`](tools/coupon_check_1100.py) from the raw answers of stage O1 (2026-11-06) and the
stored pages of 2026-11-09. Those answers carry account metadata and are kept privately by Hamza; the check names
each by its provider request ID and SHA-256, so it can be repeated on them, not from this repository alone.

## What this does not reproduce

Anything live: whether the site answers a re-ask with a genuine page or with its filters. The two replays serve
pages the collector stored on 2026-11-09 and show what the collector does with them; they do not show that the site
would answer the same way again.
