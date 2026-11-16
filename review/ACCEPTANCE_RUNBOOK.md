# Acceptance runbook: Mariano's collector 1.10.0rc5

None of these steps has been done with the client. Hamza ran the equivalent of every step on his own Azure test VM
on 2026-11-16 (where each one's record is linked below); the client's VM was not touched. A demonstration and the
acceptance on the client's VM wait for a separately authorized window (the client's restart of the VM, Hamza's SSH
access, and which Oxylabs key is used there).

Paths are relative to the repository root; `source/` is collector 1.10.0rc5 (commit `bc19afe`).

## 1. Check the package (offline, any machine with Git, Python 3.12 and uv)

```
git clone https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper
git checkout review-1.10.0rc5-20261116
sha256sum -c manifests/SHA256SUMS.txt            # every file as published
python3 manifests/check_source_tree.py           # source/ is the development tree 3f456703
cd source && uv sync --frozen
uv run marianos-collector --version              # marianos-azure-headless 1.10.0rc5
uv run pytest -q tests/unit                      # 494 passed
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/integration/test_reask_c1.py tests/integration/test_publication_result.py   # 28 and 6 passed
```

The whole integration suite (222 tests, about 26 minutes) also needs PostgreSQL's server binaries and Playwright's
Chromium (`uv run playwright install --with-deps chromium`). How each suite ran on Hamza's VM:
[`evidence/tests/`](../evidence/tests/README.md).

## 2. Install, migrate, back up, restore and roll back (a Linux VM; sudo)

```
sudo source/deploy/vm/prepare_host.sh                    # service user, database, folders
sudo source/deploy/vm/install_release.sh <wheel> <lock export> <config folder>   # a release folder; `current` moves to it
sudo marianos db-upgrade && sudo marianos sync-config && sudo marianos validate-config --check-db
sudo source/deploy/vm/backup.sh                          # database dump and configuration archive, hashed
sudo source/deploy/vm/rollback.sh                        # `current` back to the previous release (code only)
```

The parameters of each script are in [`source/docs/AZURE_VM.md`](../source/docs/AZURE_VM.md). On Hamza's VM:
[`evidence/install/INSTALL_BACKUP_RESTORE_ROLLBACK.log`](../evidence/install/INSTALL_BACKUP_RESTORE_ROLLBACK.log)
(a backup restored into a scratch database with identical row counts in 26 tables, then 1.10.0rc5 installed on its
own database, migrated to 0006, rolled back to 1.10.0rc3 and forward again).

## 3. The container (Docker)

```
cd source
docker build --build-arg SOURCE_COMMIT=bc19afe60c1016cf5d08d055abd96bc69c9d3dd1 -t marianos-collector:1.10.0rc5 .
docker run --rm marianos-collector:1.10.0rc5 --version
docker run --rm marianos-collector:1.10.0rc5 validate-config
```

On Hamza's VM: image `sha256:df52af770f1a2509cad91281f6a9dfbe4d58a4998bfb23fd01f9838df2eafcf9`, `--version`, the build record, `validate-config` and, against PostgreSQL,
`validate-config --check-db` and `status`, all exit 0
([`evidence/install/container/`](../evidence/install/container/)).

## 4. Check the runs and the data (offline)

```
python3 -I evidence/samples/check_sample.py evidence/samples/F2 --random 20   # records against their source tiles
python3 -I evidence/samples/check_sample.py evidence/samples/L1 0084024314377 # one named UPC (rows 22 to 27: L1)
```

Each run's folder in [`evidence/runs/`](../evidence/runs/) holds its stage record, its run report, the dataset, the
provenance of every record, every page answer with its verdict, the requests set aside, the ledger rows and the log
([`evidence/README.md`](../evidence/README.md)).

## 5. Observe a small live run (client present; paid; needs the owner's approval of its ceiling)

Every paid command goes through the shared ledger's gate (reserve before dispatch). On Hamza's VM this is the
harness `mstage` around the collector; on the client's VM the same gate, or the collector's own ceiling alone if the
client's account is used:

```
sudo marianos set-ceiling --provider oxylabs --submissions 130 --usd 0.195 --reason "<who approved, when>"
sudo marianos run --store marianos-53100502-pickup --categories 22,23,24,25,26,27 --max-credits 130
sudo marianos status --store marianos-53100502-pickup
```

As it ran on Hamza's VM (1.10.0rc4, one lane): [`evidence/runs/L1/`](../evidence/runs/L1/RUN_REPORT.md).

## 6. Observe a stop, a refused start, a kill and the recovery (same session; paid)

`systemctl stop <unit>` (SIGTERM) stops the run resumably (exit 75); a second start for the store is refused before
any request (exit 9); a hard kill (SIGKILL) leaves the requests in flight held as unknown, charged against the
ceiling, and the next `resume` recovers the abandoned segment once its lease has expired. A stop at the spending
ceiling is different: the collector finalizes the run there (exit 4), as a partial dataset that is never published
(observed in P2, P5 and at the end of F2). A run that is to be continued in a later window is therefore stopped with
SIGTERM before its ceiling, or by the segment time limit (`max_segment_minutes`), both resumable. As it ran on Hamza's VM,
within the full run F2 under two lanes, with a reboot of the VM between two slices: [`evidence/operations/`](../evidence/operations/README.md) and the
recorded walkthrough ([`evidence/walkthrough/`](../evidence/walkthrough/README.md)).

## 7. Close the session

No collector unit may be left running (`systemctl list-units 'marianos-*'`); the schedule stays off unless the
client decides otherwise; the ledger's status is read and kept with the session's evidence.

## 8. What remains open

[`OUTSTANDING.csv`](OUTSTANDING.csv): one row per open item, with its owner, what blocks it, the evidence that
would close it and the next action.
