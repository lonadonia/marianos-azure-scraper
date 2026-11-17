# Installation, migrations, backup, restore, rollback and the container: 1.10.0rc6

Everything here ran on Hamza's own Azure test VM (Ubuntu 24.04, PostgreSQL 16, Docker 29.1.3) on 2026-11-16, with
the scripts the collector ships in [`source/deploy/vm/`](../../source/deploy/vm/). None of these steps sent a request
to the provider, and the client's VM was not touched.

The candidate is commit `d77f306`, Git tree `b6b5f1d3`. Its tree was sent to the VM as an archive and extracted
there. The tree ID was computed on the VM and checked against the pinned one before the suites ran
([`../tests/vm_suites_d77f306/`](../tests/vm_suites_d77f306/)). The wheel and the lock export were then built from
that same extraction.

| File | What it shows |
|---|---|
| [`vm_install_rc6.log`](vm_install_rc6.log) | One session, 23:09:35Z to 23:10:03Z ([`vm_rc6_install.sh`](vm_rc6_install.sh)), in this order:<br>1. The release files match their recorded hashes.<br>2. **Backup** of the target's database and configuration (`backup.sh`), with the dump's SHA-256 (`01a50e2f…`).<br>3. **Restore check**: the dump is restored into a scratch database with **identical row counts in 26 tables**, and the scratch database is dropped.<br>4. **Install** of 1.10.0rc6 (`install_release.sh`), and `current` moves to it.<br>5. **Migrations**: `db-upgrade` 0006 → 0006, since 1.10.0rc6 adds no migration.<br>6. `sync-config`, then `validate-config` and `status`: exit 0.<br>7. **Rollback** of the code (`rollback.sh`): `current` back to 1.10.0rc5, `validate-config` exit 0, then forward to 1.10.0rc6 again, `validate-config` exit 0. |
| [`restorecheck_rc6.txt`](restorecheck_rc6.txt) | The 26 tables' row counts, in the database and in the restored copy, side by side. |
| [`identity_rc6.log`](identity_rc6.log) | At 23:26:14Z, after the switch: `current` points to the 1.10.0rc6 release; its environment names the source commit `d77f3065c757…`; the installed version is 1.10.0rc6. **93 of 93** files of the candidate's `src/marianos_headless` (by `git archive` of `d77f306`) are identical to the installed package's files, and the installed package has no other file. |
| [`container_d77f306/`](container_d77f306/) | The container ([`vm_container.sh`](vm_container.sh)), built from the same verified tree with the repository's Dockerfile, 23:10:28Z to 23:12:26Z ([`CONTAINER.jsonl`](container_d77f306/CONTAINER.jsonl): start, end, exit code and last line of each step, one JSON record a line; its last line, `ALL_DONE`, is the driver's end marker). The image is `sha256:92332ded100a78f325f45a05f10fa86e27bc1006a9be4ee27eb243e7b831c874`, and its build information names commit `d77f3065c757b8b962524dbf8d9961dec212e72b`. In the image, `--version` gives 1.10.0rc6. `validate-config` and, against PostgreSQL, `validate-config --check-db` and `status` all exit 0. No container was left running. |

The image ID is the local image's ID on that VM. The image was not pushed to a registry, so it has no registry
digest. A rebuild elsewhere gives another ID, because the build records its own time.

## What these steps did not cover

- **The client's VM.** Nothing was installed, built or run there. The same steps are in the
  [acceptance runbook](../../review/ACCEPTANCE_RUNBOOK.md), for a separately authorized window.
- **A rollback across a migration.** 1.10.0rc5 and 1.10.0rc6 share the same database revision (0006), so the
  rollback shown is of the code only. `rollback.sh` itself says that a database migrated by a newer release is
  restored from the backup taken before the upgrade.
