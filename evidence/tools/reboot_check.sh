#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root), read only, no provider request: the state that must survive a reboot of the VM
# between two slices of one run. Run once before the reboot and once after it; the run's lines must be equal.
# Usage: reboot_check.sh LABEL DB RUN_ID > OUT
set -u
LABEL="$1"; DB="$2"; RUN="$3"
q() { sudo -u marianos psql -X -q -At -F' | ' -d "$DB" -c "$1"; }
echo "== $LABEL at $(date -u +%Y-%m-%dT%H:%M:%SZ); booted $(uptime -s) (local clock $(date +%Z))"
echo "== services"
echo "postgresql: $(systemctl is-active postgresql)"
echo "docker: $(systemctl is-active docker 2>/dev/null)"
echo "collector units active: $(systemctl list-units --no-legend --state=active 'marianos-*' | wc -l)"
echo "collector timers: $(systemctl list-timers --no-legend 'marianos-*' | wc -l)"
echo "current release: $(readlink -f /opt/marianos-collector/current)"
echo "== run (id | status | stop_code | started_at)"
q "SELECT id, status, coalesce(stop_code,'-'), started_at FROM runs WHERE id='$RUN'"
echo "== tasks by state"
q "SELECT state, count(*) FROM tasks WHERE run_id='$RUN' GROUP BY state ORDER BY state"
echo "== tasks still leased"
q "SELECT count(*) FROM tasks WHERE run_id='$RUN' AND lease_owner IS NOT NULL"
echo "== listing pages by state"
q "SELECT state, count(*) FROM listing_pages WHERE run_id='$RUN' GROUP BY state ORDER BY state"
echo "== requests set aside by state"
q "SELECT state, count(*) FROM deferred_requests WHERE run_id='$RUN' GROUP BY state ORDER BY state"
echo "== distinct UPCs observed"
q "SELECT count(DISTINCT upc) FROM product_observations WHERE run_id='$RUN'"
echo "== segments (started_at | ended_at | end_state | stop_code)"
q "SELECT started_at, coalesce(ended_at::text,'-'), coalesce(end_state,'-'), coalesce(stop_code,'-') FROM collection_segments WHERE run_id='$RUN' ORDER BY started_at"
echo "== run lock rows"
q "SELECT count(*) FROM run_locks"
echo "== ledger"
mstage ledger-status | python3.12 -I -c 'import json,sys; d=json.load(sys.stdin); m=d["projects"]["marianos"]; print(json.dumps({"chain": d["chain"], "active_lease": d["active_lease"], "committed_usd": d["committed_usd"], "marianos": {k: m[k] for k in ("committed_usd", "spendable_in_envelope_usd", "unknown_rows", "settled_results")}}, sort_keys=True))'
