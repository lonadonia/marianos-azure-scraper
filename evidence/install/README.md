# Build, installation, backup, restore, rollback and the container

On Hamza's own Azure test VM (Ubuntu 24.04, PostgreSQL 16, Docker 29.1.3) on 2026-11-16, with the scripts the
collector ships in [`source/deploy/vm/`](../../source/deploy/vm/). No request was sent to the provider by any of
these steps. The client's VM was not touched.

## 1.10.0rc5 (commit `bc19afe`): the final candidate

| File | What it shows |
|---|---|
| [`build/tree_check.txt`](build/tree_check.txt), [`build/build.log`](build/build.log), [`build/export.log`](build/export.log) | The development tree was sent to the VM as an archive, extracted, and its Git tree ID computed there: `3f4567038890db47e83e73880e934620fdca6024`, the pinned one. The wheel, the lock export with hashes and the configuration archive were built from that tree ([`vm_build.sh`](vm_build.sh)) |
| [`INSTALL_BACKUP_RESTORE_ROLLBACK.log`](INSTALL_BACKUP_RESTORE_ROLLBACK.log) | One session, 17:06:04 to 17:06:33 UTC ([`vm_rc5_install.sh`](vm_rc5_install.sh)): the release files match their recorded hashes; **backup** of the previous target's database (`backup.sh`); **restore check**: that dump restored into a scratch database and the row counts of all 26 tables compared, identical ([original](RESTORE_CHECK_ORIGINAL_COUNTS.txt), [restored](RESTORE_CHECK_RESTORED_COUNTS.txt)), scratch database dropped; a new database and data folder for the candidate (`prepare_host.sh`), so that its runs share nothing with the earlier candidate's; **installation** from the wheel and the hashed lock (`install_release.sh`); **migrations** to 0006 (`db-upgrade`), `sync-config`, `validate-config --check-db`, `status`; **rollback** (`rollback.sh`): `current` back to 1.10.0rc4, its configuration and database check passing, then forward again to 1.10.0rc5 |
| [`container/`](container/) | The real container ([`vm_container.sh`](vm_container.sh)), built from the same verified tree with the repository's Dockerfile, 17:06:39 to 17:08:47 UTC ([`CONTAINER.jsonl`](container/CONTAINER.jsonl)): image `sha256:df52af770f1a2509cad91281f6a9dfbe4d58a4998bfb23fd01f9838df2eafcf9` (127,651,436 bytes as `docker image inspect` reports it); `--version` prints 1.10.0rc5; the build record inside the image names commit `bc19afe`; `validate-config`; and, against the candidate's PostgreSQL database through the host's socket as the service user, `validate-config --check-db` and `status`: every step exit 0; no container left afterwards. No key was put in the container and it sent no request |

The image ID above is the local image's ID on that VM (the image was not pushed to a registry, so it has no
registry digest); a rebuild elsewhere gives another ID because the build records its own time.

## 1.10.0rc4 (commit `570ff7c`)

[`1.10.0rc4/`](1.10.0rc4/) keeps the same records of the candidate the first live stages ran on, unchanged: its
installation with the backup, the restore check (26 tables, identical) and the rollback to 1.10.0rc3 and forward
again, and its container (image `sha256:91074c91bc2b48b04ab8e3de613a51530a1c6d299e2e92de3843a864abe2236d`).

## What these steps did not cover

- The client's VM: nothing was installed, built or run there. The same steps are in the
  [acceptance runbook](../../review/ACCEPTANCE_RUNBOOK.md) for a separately authorized window.
- A rollback across a migration: 1.10.0rc4 and 1.10.0rc5 share the same database revision (0006), so the rollback
  shown is of the code. `rollback.sh` says so itself: a database migrated by a newer release is restored from the
  backup taken before the upgrade.
