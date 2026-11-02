# Azure option B: one small Linux VM (the smallest test)

> Status: the first section, **Mariano's on its own VM (`deploy/vm/`)**, is the procedure of the test
> installation on the VM `testmarianos` (release 1.3.1, then the upgrades to 1.3.2, 1.3.3, 1.3.4 and 1.3.5); what was run there, when,
> and its output are in the delivery evidence, not in this file. The rest of this page is the earlier plan for a VM shared
> with Walmart; it was written when no Azure subscription was available and has **not** been executed.
> The Container Apps option (AZURE.md, `azure/main.bicep`) is separate and unchanged.

## Mariano's on its own VM (`deploy/vm/`)

An existing Ubuntu 24.04 VM; nothing is provisioned. Look first (`systemctl list-units`, `ss -ltnp`,
crontabs, `/opt`, `/srv`, disk, memory) and keep whatever else runs there. Everything the collector adds:

| What | Where |
|---|---|
| OS packages | `python3.12-venv`, `postgresql` (only when missing) |
| Service user (no login shell) | `marianos`; PostgreSQL role `marianos` owning the database `marianos_collector` (peer authentication on the local socket: no password) |
| Code, one folder per release | `/opt/marianos-collector/releases/<version>/` (a virtual environment installed from the wheel and the hashed lockfile export; the deploy scripts; `release.env`, the source commit every run records); `current` and `previous` link to releases |
| Configuration | `/etc/marianos-collector/config/` (the release's `config/`), `collector.env` (no secret), `oxylabs.env` (the key; mode 600, owner `marianos`) |
| Data, backups | `/var/lib/marianos-collector/{data,backups}` |
| Command | `/usr/local/sbin/marianos` → `current/deploy/marianos` |

On the workstation, from a clean checkout of the release commit:

```bash
uv build --wheel
uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.lock.txt  # with hashes
tar -czf config.tgz -C config .
scp dist/marianos_azure_headless-<version>-py3-none-any.whl requirements.lock.txt config.tgz deploy/vm/* <vm>:release/
```

On the VM (`sudo`); no script removes or overwrites anything, and running one again changes nothing:

```bash
sudo bash release/prepare_host.sh
sudo bash release/install_release.sh <version> <full commit> release/<wheel> release/requirements.lock.txt release/config.tgz
# the key goes in through standard input, never as an argument (from the workstation):
#   <key source> | ssh <vm> "sudo install -m 600 -o marianos -g marianos /dev/stdin /etc/marianos-collector/oxylabs.env"
sudo bash /opt/marianos-collector/current/deploy/backup.sh before-db-upgrade
sudo marianos db-upgrade && sudo marianos sync-config
sudo marianos validate-config --check-db --require-credentials && sudo marianos provider-balance
```

`marianos ARGS` runs one command as `marianos` through `systemd-run` with `collector.env` and the
release's `release.env` (systemd reads them as data; nothing is sourced by a shell) and waits for it. A
collection runs as a transient unit, which a lost SSH session does not stop:

```bash
sudo marianos set-ceiling ...                              # see CLI.md: no Oxylabs request without a ceiling
sudo marianos --unit marianos-run run --store marianos-53100502-pickup
journalctl -u marianos-run -f                               # its output
sudo systemctl stop marianos-run                            # SIGTERM: a resumable stop (exit 75); then `resume`
sudo marianos --at "2026-10-29 10:00:00 UTC" marianos-once status   # once, by a transient timer
```

Upgrade: `backup.sh <label>`, `install_release.sh` with the new version, `marianos db-upgrade`. Rollback
(no collector unit running): `rollback.sh` points `current` back at `previous`; a database the newer
release migrated is restored from the backup taken before (`pg_restore --clean --if-exists`) only if the
older release cannot read it. No timer or cron entry is installed for the schedules (they stay off).

## The earlier plan: one VM shared with Walmart (not executed)

Both collectors (`walmart-azure-headless` and `marianos-azure-headless`) can share one VM: one local
PostgreSQL server with one database per collector, each collector in its own folder with its own key file,
and **one collection at a time** (Walmart, then Mariano's, never both at once). No schedule is installed:
every run is started by hand until the client approves the schedules.

## Size, checked against measured use

| Resource | Proposed | Measured on the workstation, 2026-10-22 |
|---|---|---|
| VM | `Standard_B2s`: 2 vCPU, 4 GiB RAM, Ubuntu 24.04 LTS | Mariano's live run (Playwright driving Scrapfly's cloud browser over CDP: the browser runs at Scrapfly, not on the VM): **343 MB** peak for the collector's whole process tree; offline commands (`status`, `validate-export`, `export`) 87 to 117 MB. Walmart's collector has no browser driver; its live memory was not measured with the same method (the measurement then covered only the launcher process) |
| OS disk | 32 GiB Standard SSD (E4) | one local PostgreSQL: the two campaign databases are 75 MB (Walmart, 3 runs) and 49 MB (Mariano's, 3 runs). Stored pages: Walmart about **0.32 MB per result page** (the provider's answer and the page copy, compressed); Mariano's about 0.3 MB per page step (page copy and screenshot) |
| Network | a public IP with SSH (22) open **only** to the operator's address; no inbound web port | the collectors only make outbound HTTPS calls (Scrape.do, Scrapfly) |

4 GiB leaves room for PostgreSQL (default `shared_buffers` 128 MB), the OS and one collector at a time.
32 GiB is enough for **test and pilot runs**. It is **not** enough for a full-scope production schedule:
a full Walmart run (about 9,400 result pages, see the cost report) stores about 3 GB of page copies, so
twice weekly fills the disk in weeks. The collectors keep every page copy as evidence and have no pruning
command yet; production on a VM needs a larger data disk or a documented cleanup of old run folders
(pending).

## Permissions (no subscription-wide Owner)

**A. The client provisions the VM (preferred).** The operator needs **no Azure role at all**: an SSH login
(a Linux user with `sudo` on that VM, with the operator's public key) is enough to install, run and stop
the collectors. If the operator should also start and deallocate the VM, a custom role assigned **on that
VM only**:

```json
{
  "Name": "Collector VM operator",
  "IsCustom": true,
  "Description": "Read, start, restart and deallocate one VM; nothing else.",
  "Actions": [
    "Microsoft.Compute/virtualMachines/read",
    "Microsoft.Compute/virtualMachines/instanceView/read",
    "Microsoft.Compute/virtualMachines/start/action",
    "Microsoft.Compute/virtualMachines/restart/action",
    "Microsoft.Compute/virtualMachines/deallocate/action"
  ],
  "NotActions": [],
  "AssignableScopes": ["/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Compute/virtualMachines/<vm>"]
}
```

Optionally **Cost Management Reader** on the resource group, to read the test's cost.

**B. The operator provisions the VM (only if separately authorized).** The client creates a dedicated
resource group (e.g. `rg-collectors-test`) and assigns, **at that resource group only** and for the test
period, either the built-in **Contributor** role (it cannot assign roles or reach anything outside the
group), or this narrower custom role:

```json
{
  "Name": "Collector test provisioner",
  "IsCustom": true,
  "Description": "Create, operate and delete one test VM and its network in one resource group.",
  "Actions": [
    "Microsoft.Resources/subscriptions/resourceGroups/read",
    "Microsoft.Resources/deployments/*",
    "Microsoft.Compute/virtualMachines/*",
    "Microsoft.Compute/disks/*",
    "Microsoft.Compute/sshPublicKeys/*",
    "Microsoft.Network/virtualNetworks/*",
    "Microsoft.Network/networkSecurityGroups/*",
    "Microsoft.Network/publicIPAddresses/*",
    "Microsoft.Network/networkInterfaces/*",
    "Microsoft.DevTestLab/schedules/*",
    "Microsoft.Consumption/budgets/*"
  ],
  "NotActions": [],
  "AssignableScopes": ["/subscriptions/<sub>/resourceGroups/rg-collectors-test"]
}
```

Remove the assignment when the test ends.

## Provision (option B; option A: the client does the same)

```bash
RG=rg-collectors-test; LOC=northcentralus; VM=collectors-test; MYIP=<operator's public IP>
az vm create -g $RG -n $VM -l $LOC --image Ubuntu2404 --size Standard_B2s \
  --os-disk-size-gb 32 --storage-sku StandardSSD_LRS --admin-username collector \
  --ssh-key-values ~/.ssh/id_ed25519.pub --public-ip-sku Standard --nsg-rule NONE
az network nsg rule create -g $RG --nsg-name ${VM}NSG -n ssh-operator --priority 100 \
  --access Allow --protocol Tcp --direction Inbound --destination-port-ranges 22 \
  --source-address-prefixes $MYIP/32
# Runtime limit: deallocate automatically (this time is UTC)
az vm auto-shutdown -g $RG -n $VM --time <HHMM, 24 h after creation>
# A budget alert (an alert only: it does not stop anything)
az consumption budget create --budget-name collectors-test --amount 10 --time-grain Monthly \
  --start-date <first day of this month> --end-date <a month later> --category Cost --resource-group $RG
```

## Install (on the VM, as `collector`)

```bash
sudo apt-get update && sudo apt-get install -y postgresql unzip
curl -LsSf https://astral.sh/uv/0.13.1/install.sh | sh && . ~/.local/bin/env
mkdir -p ~/collectors ~/.secrets && chmod 700 ~/.secrets
unzip WALMART_AZURE_HEADLESS_SOURCE.zip -d ~/collectors && unzip MARIANOS_AZURE_HEADLESS_SOURCE.zip -d ~/collectors
(cd ~/collectors/walmart-azure-headless && uv sync --frozen --no-dev)
(cd ~/collectors/marianos-azure-headless && uv sync --frozen --no-dev)   # Playwright's driver only; no local browser
# One database and one role per collector (peer authentication on the local socket: no password)
sudo -u postgres createuser collector
sudo -u postgres createdb -O collector walmart_collector
sudo -u postgres createdb -O collector marianos_collector
# Keys: typed into files only the user can read (never on a command line)
install -m 600 /dev/null ~/.secrets/scrapedo.key && nano ~/.secrets/scrapedo.key
install -m 600 /dev/null ~/.secrets/scrapfly.key && nano ~/.secrets/scrapfly.key
```

`~/collectors/walmart.env` (and the same for Mariano's, with `MARIANOS_COLLECTOR_` and
`SCRAPFLY_API_KEY_FILE=~/.secrets/scrapfly.key`):

```bash
export WALMART_COLLECTOR_DATABASE_URL="postgresql://collector@/walmart_collector?host=/var/run/postgresql"
export WALMART_COLLECTOR_DATA_DIR=$HOME/collectors/data/walmart
export SCRAPEDO_API_KEY_FILE=$HOME/.secrets/scrapedo.key
```

Then, for each collector: `db-upgrade`, `validate-config --check-db --require-credentials`,
`provider-balance` (free). A first run is a pilot with limits (CLI.md), for example
`walmart-collector run --store walmart-3891-pickup --categories 4 --max-pages-per-listing 1 --max-credits 15`.
Run long collections under `tmux` or `systemd-run --user --unit walmart-run ...`, one at a time;
`systemctl --user stop walmart-run` (or Ctrl+C) sends the stop signal: the collector closes the provider
session, keeps its checkpoints and exits 75, and `resume` continues later.

## Schedules stay off

No cron entry and no systemd timer are installed, and both configurations ship with
`schedule.enabled: false`. When the client approves, a systemd timer per collector would fire at the UTC
times `schedule-info` prints (both daylight-saving offsets), running `run --store <key> --scheduled`,
which acts only on the store-local occurrence (the same logic as in Azure, tested offline).

## Stop, deallocate, clean up

* A VM shut down from inside the OS is **still billed** for compute; deallocate it from Azure:
  `az vm deallocate -g $RG -n $VM` (auto-shutdown also deallocates).
* A budget alert is **not** a hard stop; the auto-shutdown time and the operator's deallocation are.
* Before deleting, copy what must be kept: `walmart-collector export --run <id> --out <dir>` (and the
  same for Mariano's), the `data/` folders and a `pg_dump` of each database.
* Delete everything: `az group delete -n $RG --yes` (VM, disk, IP, network). Check: `az resource list -g
  $RG -o table` is empty, and no disk or public IP of the test remains in the subscription.

## Cost of the 24-hour test (estimate)

Azure retail prices (pay-as-you-go, Linux, East US and North Central US, read from the Azure Retail Prices
API on 2026-10-22): `Standard_B2s` **$0.0416/hour**; 32 GiB Standard SSD (E4) **$2.40/month**; Standard
static public IP **$0.005/hour**. A 24-hour test: about **$1.00** compute, **$0.08** disk, **$0.12** IP,
about **$1.20** in all (outbound traffic within Azure's free monthly allowance). The VM left running a
month would cost about $36 (compute $30.37, disk $2.40, IP $3.65). Prices vary by region and change; the
Azure pricing calculator for the chosen region is authoritative.
