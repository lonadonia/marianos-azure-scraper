#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root; run detached with systemd-run): the planned hard kill and recovery of one slice.
#   1. waits until UNIT's journal shows K pages collected (the run is working on both lanes);
#   2. kills every process of UNIT with SIGKILL (no handler runs: nothing is closed, released or settled);
#   3. records the unit's result, the run, its open segment, the tasks it held, the stage's ledger rows in flight
#      and the ledger lease the dead process still holds;
#   4. waits until that lease has expired (the ledger's TTL, 120 s after its last renewal), with no other action;
#   5. resumes the same run in the same open ledger stage as UNIT2 (a new lease: the ledger turns the dead lease's
#      dispatched rows into unknown outcomes, charged against the ceiling, and its never-dispatched rows into
#      released_unsent) and starts the operator's watcher beside it;
#   6. with SLICE_TARGET, starts the slice stopper beside UNIT2 (SIGTERM once the stage has SLICE_TARGET
#      reservations in the ledger, the killed execution's included), so the run stays resumable.
# Usage: kill_recover.sh UNIT UNIT2 STAGE_ID K DB LOG [SLICE_TARGET]
set -u
U="$1"; U2="$2"; SID="$3"; K="$4"; DB="$5"; LOG="$6"; SLICE_TARGET="${7:-}"
OPS=/var/lib/marianos-collector/ops-rc6
LED=/var/lib/oxylabs-marianos-20261116/ledger.sqlite3
STORE=marianos-53100502-pickup
exec >>"$LOG" 2>&1
ts() { date -u +%Y-%m-%dT%H:%M:%S.%3NZ; }
q() { sudo -u marianos psql -X -q -At -F' | ' -d "$DB" -c "$1"; }
led() {
  sudo -u marianos python3.12 -I -c '
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=15)
con.row_factory = sqlite3.Row
if sys.argv[2] == "rows":
    for r in con.execute("SELECT id, state, lease_id, purpose, created_at, updated_at FROM reservations WHERE stage_id=? AND state IN (\"reserved\",\"dispatched\",\"unknown\") ORDER BY created_at", (sys.argv[3],)):
        print(" | ".join(str(r[k]) for k in r.keys()))
else:
    r = con.execute("SELECT id, holder, acquired_at, expires_at, released_at, release_reason FROM leases ORDER BY id DESC LIMIT 1").fetchone()
    print(" | ".join(str(r[k]) for k in r.keys()))
' "$LED" "$@"
}
lease_expires() {
  sudo -u marianos python3.12 -I -c '
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=15)
r = con.execute("SELECT expires_at FROM leases WHERE released_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
print(r[0] if r else "")
' "$LED"
}
echo "== $(ts) kill_recover start: unit=$U then $U2, stage=$SID, kill after $K pages"
while :; do
  n=$(journalctl -u "$U" -o cat --no-pager 2>/dev/null | grep -c '"event": "PAGE_COLLECTED"')
  [ "$n" -ge "$K" ] && break
  systemctl is-active --quiet "$U" || { echo "== $(ts) $U ended before $K pages ($n): nothing killed"; exit 3; }
  sleep 0.5
done
echo "== $(ts) $n pages collected; in flight just before the kill:"
led rows "$SID"
echo "== $(ts) SIGKILL to every process of $U"
systemctl kill --signal=SIGKILL --kill-whom=all "$U" || systemctl kill --signal=SIGKILL "$U"
for _ in $(seq 1 60); do systemctl is-active --quiet "$U" || break; sleep 0.5; done
echo "== $(ts) unit after the kill:"
systemctl show -p ActiveState -p SubState -p Result -p ExecMainCode -p ExecMainStatus "$U"
echo "== $(ts) the run as the dead worker left it (id | status | stop_code)"
RUN=$(q "SELECT id FROM runs ORDER BY started_at DESC NULLS LAST LIMIT 1")
q "SELECT id, status, coalesce(stop_code,'-') FROM runs WHERE id='$RUN'"
echo "== open segments (id | started_at | ended_at | end_state)"
q "SELECT id, started_at, coalesce(ended_at::text,'-'), coalesce(end_state,'-') FROM collection_segments WHERE run_id='$RUN' ORDER BY started_at"
echo "== tasks held by a lease (id | state | lease_owner | lease_expires_at)"
q "SELECT id, state, coalesce(lease_owner,'-'), coalesce(lease_expires_at::text,'-') FROM tasks WHERE run_id='$RUN' AND lease_owner IS NOT NULL ORDER BY id"
echo "== run_locks"
q "SELECT store_id, run_id, holder, heartbeat_at, expires_at FROM run_locks"
echo "== ledger rows of the stage in flight or unknown (id | state | lease | purpose | created | updated)"
led rows "$SID"
echo "== latest ledger lease (id | holder | acquired | expires | released | reason)"
led lease
EXP=$(lease_expires)
echo "== $(ts) waiting until the dead lease expires at ${EXP:-none}"
if [ -n "$EXP" ]; then
  while :; do
    now=$(date -u +%s)
    end=$(date -u -d "$EXP" +%s)
    [ "$now" -gt "$end" ] && break
    sleep 2
  done
fi
sleep 3
echo "== $(ts) resuming run $RUN in the same stage as $U2"
mstage6 --unit "$U2" run "$SID" -- resume --store "$STORE"
sleep 5
systemctl is-active "$U2"
systemd-run --quiet --unit="${U2/marianos-stage-/marianos-watch-}" "$OPS/watch_stage.sh" "$U2" "$SID" "$DB" "$OPS/stages/$SID/watch2.log"
echo "== $(ts) watcher: $(systemctl is-active "${U2/marianos-stage-/marianos-watch-}")"
if [ -n "$SLICE_TARGET" ]; then
  systemd-run --quiet --unit="${U2/marianos-stage-/marianos-slicestop-}" "$OPS/slice_stop.sh" "$U2" "$SID" \
    "$SLICE_TARGET" "$OPS/stages/$SID/slice_stop2.log"
  echo "== $(ts) slice stopper for $U2 at $SLICE_TARGET reservations: $(systemctl is-active "${U2/marianos-stage-/marianos-slicestop-}")"
fi
echo "== latest ledger lease after the resume (the dead one expired, a new one acquired)"
sudo -u marianos python3.12 -I -c '
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=15)
for r in con.execute("SELECT id, holder, acquired_at, expires_at, released_at, release_reason FROM leases ORDER BY id DESC LIMIT 2"):
    print(" | ".join(str(x) for x in r))
' "$LED"
echo "== ledger rows of the stage now unknown or released unsent (id | state | lease | purpose | created | updated)"
sudo -u marianos python3.12 -I -c '
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=15)
for r in con.execute("SELECT id, state, lease_id, purpose, created_at, updated_at FROM reservations WHERE stage_id=? AND state IN (\"unknown\",\"released_unsent\") ORDER BY created_at", (sys.argv[2],)):
    print(" | ".join(str(x) for x in r))
' "$LED" "$SID"
echo "== $(ts) kill_recover done"
