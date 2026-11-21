# Acceptance runbook: Mariano's collector 1.10.0rc6

None of these steps has been done with the client. Hamza ran the equivalent of every step on his own Azure test VM
on 2026-11-17 (where each one's record is linked below); the client's VM was not touched. A demonstration and the
acceptance on the client's VM wait for a separately authorized window (the client's restart of the VM, Hamza's SSH
access, and which Oxylabs key is used there).

Paths are relative to the repository root; `source/` is collector 1.10.0rc6 (commit `d77f306`).

## 1. Check the package (offline, any machine with Git, Python 3.12 and uv)

```
git clone https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper
git checkout review-1.10.0rc6-20261117
sha256sum -c manifests/SHA256SUMS.txt            # every file as published
python3 manifests/check_source_tree.py           # source/ is the development tree b6b5f1d3, file by file
cd source && uv sync --frozen
uv run marianos-collector --version              # marianos-azure-headless 1.10.0rc6
uv run pytest -q tests/unit                      # 506 passed
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/integration/test_reask_c1.py tests/integration/test_publication_result.py   # 30 and 6 passed
```

The whole integration suite (247 tests, about 28 minutes) also needs PostgreSQL's server binaries and Playwright's
Chromium (`uv run playwright install --with-deps chromium`). How each suite ran on Hamza's VM, and each correction's
tests before and after: [`evidence/tests/`](../evidence/tests/README.md).

## 2. Install, migrate, back up, restore and roll back (a Linux VM; sudo)

```
sudo source/deploy/vm/prepare_host.sh                    # service user, database, folders
sudo source/deploy/vm/backup.sh                          # database dump and configuration archive, hashed
sudo source/deploy/vm/install_release.sh <wheel> <lock export> <config folder>   # a release folder; `current` moves to it
sudo marianos db-upgrade && sudo marianos sync-config && sudo marianos validate-config --check-db
sudo source/deploy/vm/rollback.sh                        # `current` back to the previous release (code only)
```

The parameters of each script are in [`source/docs/AZURE_VM.md`](../source/docs/AZURE_VM.md). On Hamza's VM:
[`evidence/install/vm_install_rc6.log`](../evidence/install/vm_install_rc6.log) (the target's backup restored into a
scratch database with identical row counts in 26 tables, then 1.10.0rc6 installed on the same target as 1.10.0rc5,
migrations 0006 to 0006, rolled back to 1.10.0rc5 and forward again) and
[`evidence/install/identity_rc6.log`](../evidence/install/identity_rc6.log) (the installed package file by file
against the candidate's tree).

## 3. The container (Docker)

```
cd source
docker build --build-arg SOURCE_COMMIT=d77f3065c757b8b962524dbf8d9961dec212e72b -t marianos-collector:1.10.0rc6 .
docker run --rm marianos-collector:1.10.0rc6 --version
docker run --rm marianos-collector:1.10.0rc6 validate-config
```

On Hamza's VM: image `sha256:92332ded100a78f325f45a05f10fa86e27bc1006a9be4ee27eb243e7b831c874`, `--version`, the build record, `validate-config` and, against PostgreSQL,
`validate-config --check-db` and `status`, all exit 0
([`evidence/install/container_d77f306/`](../evidence/install/container_d77f306/)).

## 4. Check the runs and the data (offline)

```
python3 -I evidence/samples/check_sample.py evidence/samples/R7 --random 20 --seed 1               # 20 of R7's records at random, beside their source tiles
python3 -I evidence/samples/check_sample.py evidence/samples/R7 --random 20 --seed 1 --fresh-only  # 20 among the records R7 observed itself
python3 -I evidence/samples/check_sample.py evidence/samples/R7 0084024314377 0001280052496          # the two price-per-measure traces
python3 -I evidence/tools/verify_ledger_chain.py evidence/ledger/EVENTS.csv    # the spending ledger's hash chain
```

Each run's folder in [`evidence/runs/`](../evidence/runs/) holds its stage record, its run report, the dataset, the
provenance of every record, every page answer with its verdict, the requests set aside, the ledger rows and the log
([`evidence/README.md`](../evidence/README.md)).

## 5. Observe a small live run (client present; paid; needs the owner's approval of its ceiling)

Every paid command goes through a ledger's gate (reserve before dispatch). On Hamza's VM this is the harness
`mstage6` around the collector; on the client's VM the same gate, or the collector's own ceiling alone if the
client's account is used:

```
sudo marianos set-ceiling --provider oxylabs --submissions 20 --usd 0.03 --reason "<who approved, when>"
sudo marianos run --store marianos-53100502-pickup --categories 0,27
sudo marianos status --store marianos-53100502-pickup
```

As it ran on Hamza's VM (1.10.0rc6, one lane, the Coupons row and Hardware): [`evidence/runs/P7/`](../evidence/runs/P7/RUN_REPORT.md).
A run narrowed by `--categories` is a pilot: exported, never published.

## 6. Observe a stop, a refused start, a kill and the recovery (same session; paid)

`systemctl stop <unit>` (SIGTERM) stops the run resumably (exit 75); a second start for the store is refused before
any request (exit 9); a hard kill (SIGKILL) leaves the requests in flight held as unknown, charged against the
ceiling, and the next `resume` recovers the abandoned segment once its lease has expired, without asking again any
page already completed. A stop at the spending ceiling is different: the collector finalizes the run there (exit 4),
as a partial dataset that is never published (observed in the earlier deliveries: P2, P5, F2). A run that is to be
continued in a later window is therefore stopped with SIGTERM before its ceiling, or by the segment time limit
(`max_segment_minutes`), both resumable. As observed for 1.10.0rc6 on Hamza's VM: R6a's refused second start (exit 9, no request) and the operator's SIGTERM stop of R7a (exit 75, the run resumable) are in [`evidence/operations/`](../evidence/operations/README.md); R7b's hard kill (SIGKILL at 04:38:48Z, both lanes working) and its recovery in the same stage once the dead lease had expired (04:40:26Z) are in [`kill_recover_R7b.log`](../evidence/operations/slice_stops/kill_recover_R7b.log), and the walkthrough's controls (R7w: a SIGTERM stop, exit 75; a second start, exit 9; a publication of the unfinished run, exit 6) in [`evidence/walkthrough/`](../evidence/walkthrough/README.md).

## 7. Close the session

No collector unit may be left running (`systemctl list-units 'marianos-*'`); the schedule stays off unless the
client decides otherwise; the ledger's status is read and kept with the session's evidence.

## 8. What remains open

[`OUTSTANDING.csv`](OUTSTANDING.csv): one row per open item, with its owner, what blocks it, the evidence that
would close it and the next action.

## 9. 1.10.0rc7 (added 2026-11-21)

Sections 1 to 8 are kept as written for 1.10.0rc6. For 1.10.0rc7, `source/` is collector 1.10.0rc7 (commit
`ec10cde`, package tree `fe89f133`). Nothing in this section has been done with the client, and no step of it sends
a request to the retailer or to a provider.

**Check the package (offline).** As in section 1, at the tag `review-1.10.0rc7-20261121`:

```
python3 manifests/check_source_tree.py           # source/ is the development tree fe89f133, file by file
python3 -I manifests/check_links.py              # every repository link resolves; no web address is visited
cd source && uv sync --frozen
uv run --frozen marianos-collector --version     # marianos-azure-headless 1.10.0rc7
uv run --frozen pytest -q tests/unit             # 533 passed
uv run --frozen pytest -q tests/integration/test_reask_c1.py tests/integration/test_publication_result.py   # 30 and 6 passed
uv run --frozen pytest -q tests/integration/test_route_audit_rc7.py tests/integration/test_lanes_or24.py
```

The whole integration suite on 1.10.0rc7: 260 tests (browser tests included), about 43 minutes on
the workstation.

**Check the coverage verdict (offline).** Each listing's verdict is in the export's coverage files
(`coverage_reconciliation.csv`: `expected_identities`, `accounted_identities`, `missing_identities`,
`unexpected_identities`, `cursor_status`, `status`). A listing is DONE only with `missing_identities` and
`unexpected_identities` at 0; the publication refuses (exit 6) a run with an unexplained gap. To read a stored run
again against the 1.9 baseline: `source/tools/replay_routes.py` ([`evidence/rc7/README.md`](../evidence/rc7/README.md)).

**Check records strictly (offline).**

```
python3 -I evidence/samples/selftest_check_sample.py evidence/samples/R7            # selftest: PASS
python3 -I evidence/samples/check_sample.py evidence/samples/R7 --strict --expect evidence/rc7/accuracy/EXPECTED_27021_R7.txt   # exit 0
python3 -I evidence/samples/check_sample.py evidence/samples/R7 --strict --expect evidence/rc7/accuracy/EXPECTED_27017_R7.txt   # exit 1: 24 missing
```

**Live steps (sections 5 and 6) on 1.10.0rc7: held.** They need Darren's separate decision. The proposed first one
reads only Dog Food 27017 and Cat Treats 27022 with two lanes, the three named product pages included, with at most
45 submissions, USD 0.07 at the ledger's list rate and 30 minutes, and no publication (the addendum, section 7). It
passes only when both listings' exact UPC sets are accounted for. Installation, migrations, backup and restore,
rollback and the container (sections 2 and 3) are unchanged by 1.10.0rc7 and were not run again for it.
