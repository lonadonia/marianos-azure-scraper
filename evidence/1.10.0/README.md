# Evidence of release 1.10 (2026-11-12): the offline C1 candidate

Collector **1.10.0rc3** ([`source/`](../../source/)): development commit `a1040f79919b8e876e0b69cd909cecf9363780b4`, collector tree
`22ebcf96cdb2021347f0e0e4d7506ad4c36d2c10`. The report that cites these files is
[`review/TECHNICAL_REPORT_1.10.0.md`](../../review/TECHNICAL_REPORT_1.10.0.md). Times are UTC.

**Everything here is offline.** No request was sent for this release: no provider, no retailer, no trial credit,
no client account, no VM, no SSH, no Azure test. Every result names its revision, where it ran (Hamza's workstation:
Windows 11, CPython 3.12.10) and what kind of evidence it is:

- **SYNTHETIC**: pages built by the tests (`tests/c1_site.py`), served through a mock transport, with a fake clock;
- **OFFLINE REPLAY**: pages the collector itself stored on 2026-11-09, copied byte for byte into
  [`source/tests/fixtures/oxylabs_2026-11-09/`](../../source/tests/fixtures/oxylabs_2026-11-09/) and served again
  (origins, request IDs and hashes in its `SOURCES.json`). A replay shows what the collector does with those answers,
  not that the site would give them again;
- **SAVED SOURCE CHECK**: a reading of answers saved on 2026-11-06 and 2026-11-09, without a request.

The evidence of 1.9 ([`evidence/1.9.0/`](../1.9.0/README.md)) and 1.8 is unchanged, and none of it is relabelled
as evidence for 1.10.0rc3.

## Files

| Path | What it holds |
|---|---|
| [`c1/CASES_BEFORE_AFTER.csv`](c1/CASES_BEFORE_AFTER.csv) | the 28 tests of `test_reask_c1.py`, one per line: its case (1 to 5 of the brief), kind (control, or what C1 adds), evidence type, outcome on 1.9.0rc4 and on 1.10.0rc3, the first line of its failure on 1.9.0rc4, and whether that is as expected |
| [`c1/cases/`](c1/cases/) | what each test observed, per revision, written before it was judged: listing pages and verdicts, requests set aside with every answer, records, coverage, gates, ledger, export files and the published pointer (26 files per revision: the two replay controls read the saved pages directly and write none). The 1.9.0rc4 files say `uncommitted_changes: true` because the collector's own revision check counts the added, untracked test files; no tracked file of 1.9.0rc4 was changed (`worktree_modified_tracked_files: []` in [`tests/rc4_c1_cases.json`](tests/rc4_c1_cases.json)) |
| [`c1/junit/`](c1/junit/) | the two JUnit result files the table is made from |
| [`c1/RC4_OVERLAY.json`](c1/RC4_OVERLAY.json) | the 12 test files added to the unchanged 1.9.0rc4 checkout for its runs, with their SHA-256, each checked against the candidate's file |
| [`publication_result/`](publication_result/) | the same for the 6 tests of `test_publication_result.py` (the refused publication; kept apart from C1) |
| [`diffs/`](diffs/) | [`COMMITS.txt`](diffs/COMMITS.txt) (the five commits since 1.9.0rc4, messages and trees); each commit's diff and file list; the C1 commit split into [source, configuration and documents](diffs/C1_454b79d_source_config_docs.diff) and [tests](diffs/C1_454b79d_tests.diff) |
| [`tests/`](tests/) | every test session of this publication: for each, its record (`.json`: command, revision, clean tree, environment, UTC times, counts, skips, exit code, verdict, log hash) and its complete output (`.log`); [`SESSIONS.csv`](tests/SESSIONS.csv) sums them up; [`INTEGRATION_BY_FILE.csv`](tests/INTEGRATION_BY_FILE.csv) the integration suite per test file, from its [JUnit file](tests/cand_integration.junit.xml). For ruff, format and mypy the verdict is read from the tool's own line in its output (`verdict_of_the_check`, with the tool's version), since the recorder reads only pytest's summary. Kept as well: [`first_attempt_87086c1/`](tests/first_attempt_87086c1/), the first attempt on 1.10.0rc2 (`87086c1`), whose unit suite failed one test (the parser version, corrected in 1.10.0rc3) while ruff, format and mypy passed; and [`superseded_tests_of_cf3b8eb/`](tests/superseded_tests_of_cf3b8eb/), the first runs of the before-cases on 1.9.0rc4 with the test files of `cf3b8eb`: the same counts, run again because three staged cases had left no observation where they failed. The `x_` sessions ran in a clean extraction of the candidate's tree, checked file for file against it before its install, before its sessions and after them ([`x_tree_check.json`](tests/x_tree_check.json); [after](tests/x_tree_check_after_sessions.json): nothing missing or changed, 79 files added under `.hypothesis/`, the property tests' example database); a first extraction, whose line ends the workstation's Git settings had converted, was replaced before any session ran in it ([record](tests/x_tree_check_first_extraction.json)) |
| [`coupons/COUPON_EVIDENCE_CHECK.json`](coupons/COUPON_EVIDENCE_CHECK.json) | the client's four coupon examples in the saved sources: each saved product page, whether the provider rendered it, whether it has a Savings section, and the coupons it names |
| [`budget/NEXT_STAGES.json`](budget/NEXT_STAGES.json) | the proposed live stages S6 and S6b: **not run, not approved**; S7 and full collection deferred |
| [`budget/LEDGER_STATUS.json`](budget/LEDGER_STATUS.json) | the shared trial ledger as read for this publication (read only; its hash chain verified); nothing was reserved or spent |
| [`corrections/LINE_ENDS_190.json`](corrections/LINE_ENDS_190.json) | the 85 files of `evidence/1.9.0/` whose Windows line ends 1.9 wrote as LF without a record: for each, the private original's SHA-256 and size, the published hash, the count of line ends, whether writing each LF back as CRLF gives the original, and whether its run's `exports/manifest.json` names that original; with the check of the 596 archive files of 1.8 (all match). Corrected rows: [`manifests/REDACTIONS.csv`](../../manifests/REDACTIONS.csv), [`manifests/FILE_MAP.csv`](../../manifests/FILE_MAP.csv) |
| [`QUALIFICATION_EVIDENCE_REQUIREMENTS.md`](QUALIFICATION_EVIDENCE_REQUIREMENTS.md) | what the later live evidence must contain (dataset, source provenance, logs, run report), fixed before any of it exists |
| [`REPRODUCE.md`](REPRODUCE.md) | the exact offline commands: the candidate's suites, the same cases on 1.9.0rc4 and on the candidate, the tables |
| [`tools/`](tools/) | the scripts that produced these files |

## Results in brief

| What | 1.9.0rc4 (`8abc2c1`) | 1.10.0rc3 (`a1040f7`) |
|---|---|---|
| C1: 7 controls | 7 passed | 7 passed |
| C1: 21 cases of what C1 adds | 21 failed | 21 passed |
| Publication result: 3 controls | 3 passed | 3 passed |
| Publication result: 3 cases of the correction | 3 failed | 3 passed |
| Unit suite | (488 passed, 1.9's own run) | 494 passed |
| Integration suite, PostgreSQL | (183 passed, 1.9's own run) | 218 passed |
| ruff, format, mypy | clean (1.9's own run) | clean |

## What was changed for publication

Windows line ends (CRLF) are written as LF. In the five JUnit result files, the workstation's computer name
(pytest's `hostname` attribute) is written `<workstation>`. Nothing else needed masking: no file here holds the
workstation's user folder, its projects folder or a provider key's fingerprint (the build's masking pass found none). The session
records point to their published log and carry its hash beside the private one; the lint records also carry the
verdict read from the tool's own output and the tool's version. Each changed file is in
[`manifests/REDACTIONS.csv`](../../manifests/REDACTIONS.csv) with its original and published SHA-256. Logs keep the
working folders (`C:\m8\...`) as written.

## What is not here

- Any live result for 1.10.0rc3: there is none.
- The raw provider answers and stored pages read by the coupon check, which carry account metadata: kept privately
  by Hamza, named by request ID and SHA-256.
