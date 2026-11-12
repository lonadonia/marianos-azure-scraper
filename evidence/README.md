# Evidence index

These files come from `MARIANOS_EVIDENCE_1.8.0rc5.zip` (SHA-256 `7dc352c5ccca19a0ac73a916ad0df00c8f765338de11d91cb077e6981de7e026`)
and, for the census estimate, the ledger and segment tables and the package verification, from the delivery folder.
They are unchanged except for the redactions in [`manifests/REDACTIONS.csv`](../manifests/REDACTIONS.csv), each with
both SHA-256 values, and one label correction in `census/FULL_SCOPE_ESTIMATE.json`
([`manifests/DOC_CORRECTIONS.md`](../manifests/DOC_CORRECTIONS.md)). [`manifests/FILE_MAP.csv`](../manifests/FILE_MAP.csv)
maps every original path to its path here; older documents and logs write archive paths as `E:<path>` or
`runs/<run id>/`.
References written `D170:` or `D150:` name files of the earlier 1.7.0rc2 and 1.5.0 deliveries, which are not
republished here. Logs keep the workstation's working-folder paths (such as `C:\m6\...`) as they were written.

## Release 1.10 (2026-11-12): the offline C1 candidate

[`1.10.0/`](1.10.0/README.md): the C1 cases and the publication-result cases on 1.9.0rc4 and on 1.10.0rc3 (each
test's outcome and observation on both), the diffs since 1.9.0rc4, the test sessions of the candidate, the coupon
examples checked in the saved sources, the proposed stages S6 and S6b (not approved) and what the later live
evidence must contain. Nothing in it is live.

## Release 1.9 (2026-11-06 to 2026-11-09)

[`1.9.0/`](1.9.0/README.md): the live stages of 2026-11-06 (O1, S1, O2) and of 2026-11-09 on 1.9.0rc3 (S1b, S4,
S5a, S5b, S3) and 1.9.0rc4 (S5b2, S4b, S4c, S3b, S4d): logs, stage records, the runs' tables and exports, the
paging census, the exact incomplete queue; the M2 to M5 analyses, the T05, T06, T07, N09 and two-lane reproductions, the adapter's identities,
the test sessions of 1.9.0rc3, 1.9.0rc4 and probe 1.7.3, the
shared trial ledger's Mariano's rows and the proposed next stages. Everything below is the 1.8 evidence, as
published.

## Live evidence: Oxylabs Web API, Vernon Hills 53100502 PICKUP, from Hamza's workstation

No live request was made with 1.8.0rc5. Each run folder holds the run's database tables (`<run>/db/`), its
export (`<run>/data/exports/`) and the stored pages (`<run>/data/live/`).

| Folder | Release | What it shows |
|---|---|---|
| [`live-runs/Q1_1.8.0rc1_01M6E2XXQNX1FYXPM37FGTYCKQ/`](live-runs/Q1_1.8.0rc1_01M6E2XXQNX1FYXPM37FGTYCKQ/) | 1.8.0rc1 `3b2650a` | stopped by its canary (defect T01); rejected |
| [`live-runs/Q1b_1.8.0rc2_01M6E3RDEBPZ39SVR37JR6PE8F/`](live-runs/Q1b_1.8.0rc2_01M6E3RDEBPZ39SVR37JR6PE8F/) | 1.8.0rc2 `b1d69d1` | stopped as ABNORMAL_RESULT on the new card variant (T02); rejected |
| [`live-runs/Q1c_1.8.0rc3_01M6E49AHDXSQA04JQZ0HZ40GH/`](live-runs/Q1c_1.8.0rc3_01M6E49AHDXSQA04JQZ0HZ40GH/) | 1.8.0rc3 `ec3b6fe` | rows 23-26 complete, 362 products and 351 valid; a hard kill and resume; published locally |
| [`live-runs/Q2_1.8.0rc4_01M6E5V6CASQ8F00VC8PE9TFYW/`](live-runs/Q2_1.8.0rc4_01M6E5V6CASQ8F00VC8PE9TFYW/) | 1.8.0rc4 `9d16475` | rows 22-27, 1,160 products and 1,137 valid; a planned kill, an unplanned stop and a resume; rejected by G3 and G13 ([dataset](../data/Q2-1.8.0rc4/)) |
| [`live-runs/qualification/`](live-runs/qualification/) | | the qualification configuration, the run script, the segment logs and the kill records |
| [`live-runs/db_global/`](live-runs/db_global/) | | the database's shared tables: runs, publications and the last-good pointer, settings and the audit log |
| [`live-runs/SHA256SUMS.extract.txt`](live-runs/SHA256SUMS.extract.txt) | | the original archive's checksums of these run files, written with their archive paths (`runs/<run id>/...`) |
| [`live-probes/`](live-probes/) | | probes L0-L20 (the provider's options and the pages tried) and K1 (store location through the Kroger certification API) |
| [`census/`](census/) | | stage D: one page per department and the full-scope estimate behind [`COST_AND_RUNTIME_REPORT.md`](../review/COST_AND_RUNTIME_REPORT.md) |
| [`accounting/`](accounting/) | | every provider submission ([`REQUEST_LEDGER.csv`](accounting/REQUEST_LEDGER.csv)), every run segment with its release and commit ([`SEGMENTS.csv`](accounting/SEGMENTS.csv)), and the task's budget ledger |

**Withheld:** the qualification database dump (`db_dump/marianos_q180.sql`) is not published, because it is a private
database dump. Its SHA-256 is still listed in `live-runs/SHA256SUMS.extract.txt`, and the tables that the claims rely on
are in each run's `db/` folder and in `db_global/`.

## Offline evidence

| Folder | Release | What it shows |
|---|---|---|
| [`rc5-offline/`](rc5-offline/) | 1.8.0rc5 `ee5ec99` | the build; the new G13 regression, failing on rc4 and passing on rc5; the integrity re-check of the live runs under rc4 and rc5; the full suite, 576 passed in 26:02 ([`t_full_rc5_x19b.log`](rc5-offline/t_full_rc5_x19b.log)) |
| [`tests/`](tests/) | rc1-rc4 | test sessions by candidate, including rc4's full suite from a clean extraction, 574 passed ([`t_full_rc4_x18.log`](tests/t_full_rc4_x18.log)); [`regress/`](tests/regress/) holds the pagination regressions on 1.7.0rc2 (6 failed) and on 1.8.0 (6 passed), and the mutation check (8 of 11 mutants run, each caught by a test; the 9th timed out in the workstation's standby and the runner stopped, so 3 were not run) |
| [`offline-reprocessing/`](offline-reprocessing/) | | the client's findings reproduced from 1.7.0rc2's stored pages, the 1.8.0 rules over 1.7.0rc2's records, and the price-conflict trace |
| [`classic-probe/`](classic-probe/) | probe 1.6.0 | offline probe sessions from the rc4 and rc5 source archives, and the provider's public documentation as captured on 2026-11-02 |
| [`walkthrough/`](walkthrough/) | rc4 live, rc5 offline | the recordings behind the [videos](../walkthrough/), each step's raw output and the recording scripts |
| [`plan/TEST_PLAN_180.md`](plan/TEST_PLAN_180.md) | | the test plan and its amendments, each written before the requests it governs |
| [`verification/PACKAGE_VERIFICATION.txt`](verification/PACKAGE_VERIFICATION.txt) | | the verification of the original delivery from a fresh extraction of its archives |
| [`tools/`](tools/) | | the scripts that produced or check this evidence, including [`check_records.py`](tools/check_records.py) |

**Void or interrupted sessions are kept and labelled, not removed.** The rc5 full suite that ran through the
workstation's standby ([`rc5-offline/t_full_rc5_x19.log`](rc5-offline/t_full_rc5_x19.log)) is void: its one failure
passed alone and in the full rerun. The interrupted rc1-rc3 sessions are described in
[`TECHNICAL_REPORT.md`](../review/TECHNICAL_REPORT.md) §14.
