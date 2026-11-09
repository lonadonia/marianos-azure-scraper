# Acceptance runbook: Mariano's collector 1.9.0rc4

This runbook lets the client check what this delivery claims, on any machine with Python 3.12, `uv` and Git, and on
the client's own Azure VM. Steps 1 to 4 are **offline**: they send no request to Mariano's or to any provider.
Steps 5 and 6 are **live and paid**. They need an approved route, account and allowance, and none has been
approved for the client's VM. Steps marked **client** are the client's own.

None of these steps has been done with the client yet. For 1.9.0rc4, Hamza ran steps 1, 3 and 4 on the delivered
trees ([`evidence/1.9.0/tests/`](../evidence/1.9.0/tests/)) and checked the published repository from a fresh clone
after the push. Step 2, the checks on the client's VM, **has not been executed**: the VM is deallocated, and at the
client's request no SSH attempt has been made ([`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md) §12). The
1.8.0rc5 runbook stays at the tag `review-1.8.0rc5-20261102`.

Paths below are relative to the repository root. `source/` is collector 1.9.0rc4 and `classic-probe-1.7.3/` the
shared Classic probe 1.7.3, each the exact Git tree of its development commit; `classic-probe/` stays the frozen
probe 1.6.0 of 1.8.0rc5 ([`manifests/PUBLICATION.json`](../manifests/PUBLICATION.json)).

## 0. What is needed first

| Item | Who | Notes |
|---|---|---|
| Python 3.12, `uv` and Git | the person checking | steps 1, 3 and 4 |
| PostgreSQL for the integration tests | the person checking | a disposable database named by `MARIANOS_COLLECTOR_TEST_DATABASE_URL`. Without it, the `pgserver` development dependency starts a throwaway server. Never point the tests at a database that holds data: they drop their tables |
| SSH access to the client's VM | **client** | step 2. The address, user and ED25519 host-key fingerprint are the client's and are not published here. Check the host key at the first connection; never disable the check |
| Docker | the person checking | step 2 (container build and start) |
| An approved route, account and allowance | **client** and Hamza | steps 5 and 6 only. Nothing in this delivery assumes one |

## 1. Check the package (offline)

```
git clone https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper
git checkout review-1.9.0rc4-20261109                      # this delivery's review tag
sha256sum -c manifests/SHA256SUMS.txt                         # every line "OK"
python3 manifests/check_frozen_trees.py                       # source/, classic-probe-1.7.3/, classic-probe/
git rev-parse HEAD:source HEAD:classic-probe-1.7.3            # the development trees (manifests/PUBLICATION.json)
git diff --stat review-1.8.0rc5-probe171-20261105 HEAD -- source   # the correction diff since 1.8.0rc5
cd source
uv sync --frozen --offline || uv sync --frozen                # the exact locked versions
uv run marianos-collector --version                           # marianos-azure-headless 1.9.0rc4
uv run ruff check && uv run ruff format --check && uv run mypy
uv run pytest -q tests/unit                                   # no database needed
uv run pytest -q -p no:randomly                               # the whole suite (needs the test database)
```

**Expected:**
- Every checksum is OK, and the frozen-tree check reports every listed file identical, none missing, different or
  extra, and the two tree ids equal to the development trees.
- The version is 1.9.0rc4, and lint, format and types are clean
  ([`wt_rc4_lint.json`](../evidence/1.9.0/tests/wt_rc4_lint.json)).
- The suites pass. On the delivered tree (development commit `8abc2c1`, clean): unit 488 passed
  ([`wt_rc4_unit.log`](../evidence/1.9.0/tests/wt_rc4_unit.log)); integration, with PostgreSQL started by
  `pgserver`, 183 passed (the full suite against PostgreSQL, 32 min 41 s) ([`wt_rc4_integration.log`](../evidence/1.9.0/tests/wt_rc4_integration.log)). 1.8.0rc5's
  576 passed in 26:02 stays its own historical result
  ([`evidence/rc5-offline/t_full_rc5_x19b.log`](../evidence/rc5-offline/t_full_rc5_x19b.log)).

The client's findings each have their own regressions:

```
uv run pytest -q tests/unit/test_client_findings_180.py        # promotions, pack size, offer terms
uv run pytest -q tests/integration/test_page_regressions.py    # the five pagination regressions of the brief
uv run pytest -q tests/integration/test_listing_pages.py       # page loop, brand-filter reading, kill and resume
uv run pytest -q tests/integration/test_last_good_survives.py  # the last-good dataset survives 7 failure kinds
uv run pytest -q tests/integration/test_vernon_hills_replay.py # saved Vernon Hills pages through the collector
uv run pytest -q tests/unit/test_partition_identity.py        # 1.9 M1: brand readings by their full identity
uv run pytest -q tests/integration/test_partitions_190.py     # 1.9 M1, M2, T07, lanes (M8), the two-lane save (rc4)
uv run pytest -q tests/unit/test_product_terms.py             # 1.9 M3 PPM flags, M4 coupon terms, M6
uv run pytest -q tests/unit/test_tiles_2026_11_06.py          # 1.9.0rc2: the tile served since 2026-11-06
uv run pytest -q tests/unit/test_tile_coupons.py              # 1.9.0rc3: a tile's coupon is unknown, not absent
uv run pytest -q tests/integration/test_tiles_listing.py      # S1's real answers through the collector
uv run pytest -q tests/integration/test_segment_end_t06.py    # 1.9 T06: each segment's end in the export
uv run pytest -q tests/unit/test_schedule_capacity.py         # 1.9 M8: the schedule's real capacity
```

`test_page_regressions.py` has the same tests that failed on 1.7.0rc2's source: 6 failed there
([`evidence/tests/regress/old_4815ed4.log`](../evidence/tests/regress/old_4815ed4.log)) and 6 passed on 1.8.0 ([`evidence/tests/regress/new_worktree.log`](../evidence/tests/regress/new_worktree.log)).

## 2. The client's VM: offline checks only (client; not executed yet)

The client allows login and offline Python and Docker checks on this VM. Provider credentials, account rates,
Classic execution and every other live collection on it are **not approved**: nothing below sends a request to
Mariano's or a provider. Use a disposable database and directory for this task only, and remove nothing else.

```
ssh -o StrictHostKeyChecking=yes <vm-user>@<vm-host>          # first connection: compare the host-key fingerprint
mkdir -p ~/marianos-190 && cd ~/marianos-190                  # this task's own folder
git clone --branch review-1.9.0rc4-20261109 https://github.com/lonadonia/marianos-azure-scraper.git && cd marianos-azure-scraper
sha256sum -c manifests/SHA256SUMS.txt && python3 manifests/check_frozen_trees.py
cd source && uv sync --frozen && uv run marianos-collector --version
uv run marianos-collector validate-config                     # configuration only; no key is read
export MARIANOS_COLLECTOR_TEST_DATABASE_URL=postgresql+psycopg://<disposable test database>
uv run pytest -q -p no:randomly                               # unit + integration, replay of saved pages
uv run ruff check && uv run ruff format --check && uv run mypy
docker build -t marianos-collector:1.9.0rc4 . && docker image inspect marianos-collector:1.9.0rc4 --format '{{.Id}}'
docker run --rm --network none marianos-collector:1.9.0rc4 --version
docker run --rm --network none marianos-collector:1.9.0rc4 validate-config
```

**Expected:** the same results as step 1. Record the commands, versions, image ID, exit codes and logs. The
container started with `--network none` shows that the offline checks need no network. Keep the database and
folder until the results are reviewed, then remove only what this step created.

**Status in this delivery: not executed.** The VM is deallocated. At the client's request no SSH attempt has been
made, no rule or key was changed and the VM was not started; the previously attached private key is not used. The
checks wait for the client to confirm a restart window and to install `scraper_client_test_v2.pub` with the old
key revoked. (1.8.0rc5: the SSH key was not loaded before the VM's automatic shutdown on 2026-11-02 15:57 UTC; the
only contact was a scan of its SSH host key at 04:47 UTC that day, no login, which matched the client's
fingerprint.)

## 3. Check the runs and the evidence (offline)

```
Q2=evidence/live-runs/Q2_1.8.0rc4_01M6E5V6CASQ8F00VC8PE9TFYW
python3 evidence/tools/check_records.py data/Q2-1.8.0rc4/products_fresh.json $Q2 10 <any number>
python3 -c "import csv;[print(r['run'],r['segment_id'],r['end_state'],r['stop_code'],r['release'],r['commit'][:7]) for r in csv.DictReader(open('evidence/accounting/SEGMENTS.csv'))]"
grep -c PICKUP $Q2/db/store_attestations.csv
```

**Expected:**
- For each record drawn at random, `check_records.py` finds the stored page that the record's provenance names. It
  recomputes the page's SHA-256 ("page hash mismatches: 0") and prints the card text beside the exported
  fields.
- Every segment of every qualification run names its release and commit (Q1 1.8.0rc1, Q1b 1.8.0rc2, Q1c 1.8.0rc3,
  Q2 1.8.0rc4). 1.8.0rc5 has not run live: its only change after 1.8.0rc4 is how the integrity gate G13 treats a
  page the provider never delivered. The killed or stopped segments are `abandoned`, with their end unknown between
  the last heartbeat and the recovery.
- Every page of Q2 is for store 53100502 (Marianos Vernon Hills, 1720 N Milwaukee Ave, 60061) and PICKUP.

**Comparing with the live site.** Opening a record's `url` on marianos.com with Marianos Vernon Hills and Pickup
selected shows **today's** prices, which may have changed since the record's `crawl_date`. A difference is
reported with its date, never "corrected".

## 4. The Classic probe (offline)

```
cd classic-probe-1.7.3                                        # the pinned shared probe; classic-probe/ is 1.6.0
uv sync --frozen && uv run pytest -q && uv run ruff check src tests && uv run mypy
uv run classic-probe --version                                # classic-probe 1.7.3
uv run classic-probe plan --targets config/targets.json       # the request-by-request plan; nothing is sent
uv run classic-probe validate --targets config/targets.json
uv run classic-probe campaign-init --manifest /tmp/cp/manifest.json --ledger /tmp/cp/ledger.jsonl --campaign-id CHECK --offline
uv run classic-probe live --manifest /tmp/cp/manifest.json    # refused: live mode is disabled in this build (exit 3)
uv run classic-probe replay --targets config/targets.json --fixtures tests/captures_marianos --rates config/rates.example.json --out /tmp/cp/replay --retailer marianos   # T05: refused in one line, exit 2, nothing created
ls /tmp/cp/replay                                             # no such folder
```

**Expected:** the tests pass (on the clean development commit `95f96a0`: 222 passed, 5 skipped,
[`evidence/1.9.0/tests/probe173_clean.log`](../evidence/1.9.0/tests/probe173_clean.log), on Windows; the five skips
are three Windows-only cases and two comparisons of the vendored files with a neighbouring collector folder that
holds another version, each copy being checked against its recorded Git blob all the same), the plan
prints the documented sequence, `live` refuses with the list of what is missing (approval, credentials, confirmed
rates; exit 3), and `replay` on a folder without `replay.json` refuses in one line with exit 2 before it creates
any folder or ledger (T05; up to 1.7.2 it ended in a traceback after creating them). The frozen 1.6.0 in
`classic-probe/` keeps its own historical result (93 passed, 2 skipped, [`evidence/classic-probe/from-1.8.0rc5-archive/probe_x19.log`](../evidence/classic-probe/from-1.8.0rc5-archive/probe_x19.log)).
[`classic-probe/CLASSIC_PROBE.md`](../classic-probe/CLASSIC_PROBE.md) has the full offline sequence, including a replay with a synthetic rate card.

## 5. Observe a small live run (client present; paid; needs approval)

**Not approved yet.** When a route, an account and an allowance are approved, on a machine where the
provider key is installed by its owner (never on a command line or in a package file):

```
marianos-collector set-ceiling --provider oxylabs --submissions 15 --usd 0.0225 --reason "client acceptance <date>"
marianos-collector run --store marianos-53100502-pickup --categories 23 --max-pages-per-listing 3 --max-credits 15
marianos-collector --pretty status --run <run id>
marianos-collector --pretty export --run <run id> --out <folder>
marianos-collector --pretty validate-export --run <run id>
```

**Expected:**
- The store check names Marianos Vernon Hills and PICKUP on every page.
- Candles Home Fragrances (row 23) is read page by page. `listing_pages.csv` lists each page with its verdict,
  new and repeated products, and its SHA-256.
- A run narrowed by limits is labelled `pilot` and is never published, by design.

## 6. Observe stop, kill and resume (same session; paid)

```
marianos-collector run --store marianos-53100502-pickup --categories 24     # Batteries, 5 pages
# in a second terminal, while it runs:
marianos-collector run --store marianos-53100502-pickup --categories 23     # refused at once, exit 9
# kill the first process hard (SIGKILL), then:
marianos-collector resume --store marianos-53100502-pickup
marianos-collector --pretty status --run <run id>
```

**Expected:**
- A single run, with the killed segment `abandoned` and its in-flight submission settled `interrupted_unknown`
  (possibly charged, counted once).
- The resume continues at the first page not completed: no completed page is requested again, and no UPC is
  recorded twice. The page that was in flight when the process was killed is requested again, and a failed request
  may be retried; every submission is in the ledger.

Q1c and Q2 showed this live on 2026-11-02 with 1.8.0rc3 and rc4 ([`evidence/accounting/SEGMENTS.csv`](../evidence/accounting/SEGMENTS.csv), [`evidence/accounting/REQUEST_LEDGER.csv`](../evidence/accounting/REQUEST_LEDGER.csv)), and so did the walkthrough
(parts 1 and 2). 1.9 names a pause by its cause (`RUN_PAUSE_REQUESTED`, `RUN_PAUSED_ON_FAILURE`; `RUN_LIMIT_REACHED`
only for a limit). On 1.9.0rc4 a graceful stop, a refused second start, a hard kill and two resumes ran live in
stage S5b2 on 2026-11-09, with no completed page asked again
([`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md) §10).

## 7. Close the session

```
marianos-collector set-ceiling --provider oxylabs --submissions 0 --usd 0 --reason "acceptance closed"
marianos-collector --pretty schedule-info --store marianos-53100502-pickup   # enabled: false
```

## 8. Setup, maintenance, recovery, adding a store or a category

These are in the source, [`source/docs/OPERATIONS.md`](../source/docs/OPERATIONS.md):
- Setup (local and Azure)
- Maintenance
- Recovery: a table of exit codes and what to do
- Adding a store
- Adding or changing categories
- The Oxylabs spending ceiling

Azure deployment is in [`source/docs/AZURE.md`](../source/docs/AZURE.md) and [`source/docs/AZURE_VM.md`](../source/docs/AZURE_VM.md).

With the Oxylabs route, a store is set by each request's `store_id` and `fulfillment_type` and checked on every
page. The "site's picker" in OPERATIONS.md's *Adding a store* applies to the Scrapfly route.

## 9. What remains open

[`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md) §15 separates the developer's remaining work from the access
and decisions needed from the client, with dated milestones. In short:

- **A run that completes its scope.** On 2026-11-09 the site answered most later pages in form B (page 1's
  products), so every 1.9 run stopped incomplete. The proposed change C1 and the stages S6, S6b and S7 are in
  [`TECHNICAL_REPORT_1.9.0.md`](TECHNICAL_REPORT_1.9.0.md) §15.
- **Full coverage at Vernon Hills Pickup.** Q2 collected CSV rows 22 to 27 as a qualification scope, and the
  stages of 2026-11-09 read parts of rows 1 to 27 (the exact queue:
  [`INCOMPLETE_QUEUE_190.csv`](../evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv)), not the client's whole category
  list. A full run needs an approved route and allowance ([`COST_AND_RUNTIME_REPORT.md`](COST_AND_RUNTIME_REPORT.md)).
- **The client's VM.** The offline checks of step 2.
- **Classic.** The probe's live mode stays disabled until the client approves it and supplies credentials,
  entitlement and confirmed rates, and no documented Classic page parameter for Mariano's page 2 was found
  ([`SHARED_CLASSIC_PROBE.md`](SHARED_CLASSIC_PROBE.md)).
- **Acceptance record.** The client confirms what they observed in steps 1 to 6.
- **Support period and IP terms.** These are subject to agreement. No terms are assumed.
- **Production schedule.** It stays disabled until the client authorizes it.
