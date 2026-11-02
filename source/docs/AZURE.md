# Azure deployment

Two options are documented separately: **A. Container Apps jobs** (this file, `azure/main.bicep`) and
**B. one small Linux VM** for the smallest test (AZURE_VM.md). Neither has been run in Azure.

> Status: the template (`azure/main.bicep`) compiles and lints without warnings (Bicep CLI 0.48.1). It
> has **not been deployed** and the image has **not been built**: no Azure subscription and no Docker were
> available where this package was prepared. A local run of the same commands (VERIFICATION.md) is not
> proof of an Azure deployment.

## Resources

| Resource | Created by the template | Purpose |
|---|---|---|
| User-assigned managed identity `marianos-collector-identity` | yes | the jobs' only identity |
| Role assignments | yes | AcrPull on the registry; Key Vault Secrets User on the vault; Storage Blob Data Contributor on this collector's container |
| Blob container `marianos-collector` | yes (in the existing account) | stored pages and site responses, exports, `published/` |
| Scheduled job per store (`marianos-53100502-pickup`; the name is a parameter) | yes | `run --store <key> --scheduled` on the store's UTC cron |
| Manual job `marianos-collector-ops` | yes | operations: `db-upgrade`, `status`, `resume`, `stop`, `finalize`, `export`, `release-hold`, ... |
| Container Apps environment + Log Analytics workspace | only with `createEnvironment=true` | runs the jobs; collects their output |
| Container registry, Key Vault, storage account, PostgreSQL server | no (existing, named by parameters) | |

Nothing in the template or the image holds a secret value.

## Prerequisites

1. A resource group with a container registry, a Key Vault using Azure RBAC authorization, a storage
   account, and an Azure Database for PostgreSQL flexible server with a database for this collector
   (e.g. `marianos_collector`; never shared with another collector).
2. Two Key Vault secrets (create them from files so no value lands in shell history, then delete the files):

   ```bash
   az keyvault secret set --vault-name <kv> --name marianos-collector-scrapfly-api-key --file scrapfly.key
   az keyvault secret set --vault-name <kv> --name marianos-collector-database-url --file database-url.txt
   ```

   The database URL is `postgresql://<user>:<password>@<server>.postgres.database.azure.com:5432/marianos_collector?sslmode=require`.
   With `databaseAuth=entra` it has no password: the job's managed identity signs in with an Entra token.
   In that case, after the first deployment, make the identity a database role, e.g. as the server's Entra
   administrator: `SELECT * FROM pgaadauth_create_principal('marianos-collector-identity', false, false);`
   and grant it rights on the `marianos_collector` database.
3. `cp azure/main.parameters.example.json azure/main.parameters.json` and fill it in (the file is
   git-ignored: it names your resources, not secrets).

## Deploy

```bash
az login
azure/deploy.sh <resource-group> <registry-name> azure/main.parameters.json
```

The script builds the image in the registry (`az acr build`, with the source commit recorded in the
image's `BUILD_INFO.json`), deploys the template, and runs `db-upgrade` through the operations job. It
starts no collection.

Then, through the operations job: `validate-config --check-db --require-credentials` and
`provider-balance`.

## Operations job

The command is written in the job's `MARIANOS_COLLECTOR_COMMAND` variable, then the job is started (the
Azure CLI cannot pass arguments that begin with `--` to `job start` reliably):

```bash
OPS=marianos-collector-ops; RG=<resource-group>
az containerapp job update -n $OPS -g $RG --set-env-vars "MARIANOS_COLLECTOR_COMMAND=status --store marianos-53100502-pickup"
az containerapp job start  -n $OPS -g $RG
az containerapp job execution list -n $OPS -g $RG -o table      # then read the execution's logs
```

Examples (`K=marianos-53100502-pickup`): `resume --store K`, `stop --store K --reason "..."`,
`finalize --store K`, `release-hold --store K --reason "..."`, `export --store K --out /tmp/x` (exports are
also in the blob container), `run --store K --categories 1 --subcategory 1:06111 --max-pages-per-listing 1
--max-products 10` (a pilot).

## Schedule, continuation and daylight-saving time

Azure evaluates cron expressions in UTC; the store's schedule is in its own time (America/Chicago). A
full-scope run lasts longer than one execution (OPERATIONS.md, Capacity), so with
`schedule.continue_unfinished: true` (the shipped setting) the job fires **every 30 minutes**
(`*/30 * * * *`: each store's `cronUtc` in the `schedules` parameter of `azure/main.bicep`) and each firing
decides once and exits. `run --scheduled`:

1. exits 0 (`SCHEDULE_OFF`) while the schedule is off (the shipped state, until the client approves it);
2. at the store-local start time of a scheduled weekday (Mon + Thu 07:00 by default; up to 5 minutes early,
   up to `start_tolerance_minutes` late, 45 by default): exits 8 (`COLLECTION_HELD`) if the store is held;
   reports a finished occurrence (`OCCURRENCE_DONE`, with its outcome's exit code) or continues its
   unfinished run (`OCCURRENCE_CONTINUED`); otherwise closes an unfinished run of an earlier occurrence as
   partial (`RUN_SUPERSEDED`: exported, never published) and starts the new run;
3. at any other firing inside the daily window (07:00 to 19:00 local, any weekday): continues the store's
   unfinished scheduled run (`OCCURRENCE_CONTINUED`, `"continuation": true`), unless another execution is
   collecting it (exit 9, `STORE_BUSY`) or the store is held (exit 8);
4. otherwise exits 0 in seconds (`NOT_DUE`, with the next local start).

Because the decision is made in store-local time, a daylight-saving change never moves or doubles a run.
One execution collects for at most `limits.max_segment_minutes` (300, below the job's 360-minute replica
timeout) and then pauses the run at its checkpoint (`SEGMENT_DURATION_LIMIT`, exit 75): the run is not
finalized or published there. A scheduled run that reaches the window's end pauses the same way
(`SCHEDULE_WINDOW_END`) and continues in a later day's window. The whole run is bounded by
`limits.max_run_minutes` (2880: 48 hours of active collection over all its executions) and by its credit
budgets, which are counted across executions and never reset by a continuation. A continued run keeps the
scope, limits and counters recorded at its start; its finished listings, page checkpoints (Load More
cursors; with Oxylabs from 1.8.0, the `listing_pages` table) and
observations are checkpointed, so a continuation neither repeats nor skips them, and each new browser
session selects and verifies the store again before collecting.

The next occurrence closes an unfinished run (point 2). With Monday and Thursday starts and a 07:00 to
19:00 window, a run has about 36 hours of window time from a Monday start (48 from a Thursday start)
before it is superseded. A superseded run is a partial dataset: it is exported and never published, and
the products it verified remain part of the store's retained assortment for later runs.

`marianos-collector schedule-info --store <key>` prints the start-only expression (`cron_utc`, for both UTC
offsets) and, with continuation on, `cron_utc_with_continuation`. There is no scheduler inside the
collector: each execution decides once and exits.

## Overlap, timeouts and retries

* **Overlap.** Each execution runs one replica (`parallelism: 1`). Two executions for the same store (a
  manual one during a scheduled one, or a slow run reaching the next firing) cannot collect at once: the
  store lock (a PostgreSQL advisory lock plus a lock row) refuses the second one (exit 9, `STORE_BUSY`).
* **Timeouts.** `replicaTimeout` is 21,600 s (6 h); the collection's own `max_segment_minutes` (300)
  pauses the execution first, resumably, and a later firing continues the run (above). If Azure stops an
  execution (timeout or a manual stop), the collector receives SIGTERM:
  it closes the cloud browser, keeps the run's checkpoints, marks the run `interrupted` (`TERMINATED`),
  releases the store lock and exits 75. A browser an execution could not close (the replica was killed)
  is closed by Scrapfly at its session timeout (`session_timeout_s`, 900 s).
* **Retries.** Inside an execution: a lost cloud browser session is reopened a bounded number of times
  (the store is selected again); a run stopped by a transient provider failure is resumed up to
  `max_auto_resumes` times. Azure retries a failed execution once (`replicaRetryLimit: 1`);
  that retry continues or reports the same occurrence, never starts a second one. A refusal, a store
  mismatch or a failed canary is never retried: the store is held until `release-hold`.

## Identity and secrets

The jobs use one user-assigned identity, only for this collector:

* image pull from the registry (AcrPull);
* the two Key Vault secrets, referenced by the jobs as Container Apps secrets
  (`SCRAPFLY_API_KEY`, `MARIANOS_COLLECTOR_DATABASE_URL`);
* blob read/write on its own container (`MARIANOS_COLLECTOR_STORAGE=azure_blob`, `AZURE_CLIENT_ID` selects
  the identity for `DefaultAzureCredential`);
* optionally the database itself (`MARIANOS_COLLECTOR_DATABASE_AUTH=entra`).

The Walmart collector is deployed from its own project with its own identity, secrets, database,
container and jobs; neither can read the other's secrets or state. Their logs are told apart by job name.

## What runs where

* **Azure (this deployment):** the collector's code, the schedule's firing, the database, the blob
  storage, the secrets, the logs. No browser runs in Azure.
* **Scrapfly:** the cloud browser itself (a Chromium with a residential US proxy, run in Scrapfly's
  infrastructure), driven by the job over CDP; it loads marianos.com, and Scrapfly therefore sees the
  pages, the store selection and the traffic of the session. Scrapfly's Account API reports the credit
  balance. Scrapfly does not see the database, the exports or the configuration.
* **Mariano's:** serves the pages and their product data to the cloud browser.

## Costs to expect

Container Apps jobs bill per execution (vCPU-seconds and GiB-seconds; a skipped firing runs for a few
seconds); Log Analytics bills ingestion; PostgreSQL and storage bill as usual. Scrapfly bills the cloud
browser's session time and bandwidth in API credits (the free plan has 1,000 a month): an earlier run of
125 products over 9 page steps used about 255. Use `limits.max_credits_per_run`, `max_credits_per_day`
and `min_credit_reserve` to bound spending; extra usage stays off unless enabled on the Scrapfly account.
