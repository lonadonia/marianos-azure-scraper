#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root; started detached with systemd-run beside a slice's unit). Ends one slice of the full
# run resumably: in 1.10.0rc4 and rc5 a stop at the spending ceiling finalizes the run, so a slice to be continued
# is stopped by the operator with SIGTERM (systemctl stop: the collector leaves the run interrupted, exit 75) once
# the stage has TARGET reservations in the shared trial ledger; the stage's ceiling (in the collector and the
# ledger) stays above TARGET as the backstop. Polls the ledger read-only once a second. Logs to LOG.
# Usage: slice_stop.sh UNIT STAGE_ID TARGET LOG
set -u
U="$1"; SID="$2"; TARGET="$3"; LOG="$4"
LED=/var/lib/oxylabs-marianos-20261116/ledger.sqlite3
exec >>"$LOG" 2>&1
ts() { date -u +%Y-%m-%dT%H:%M:%S.%3NZ; }
count() {
  sudo -u marianos python3.12 -I -c '
import json, sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=15)
rows = dict(con.execute("SELECT state, count(*) FROM reservations WHERE stage_id=? GROUP BY state", (sys.argv[2],)).fetchall())
print(sum(rows.values()), json.dumps(rows, sort_keys=True))
' "$LED" "$SID"
}
echo "== $(ts) slice_stop start: unit=$U stage=$SID target=$TARGET reservations"
# Fail closed: a stage id the ledger does not hold open would never reach the target (the run would go on to its
# ceiling, where the collector finalizes it); stop the unit now, resumably, instead.
open_stage=$(sudo -u marianos python3.12 -I -c '
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=15)
print(con.execute("SELECT count(*) FROM stages WHERE stage_id=? AND closed_at IS NULL", (sys.argv[2],)).fetchone()[0])
' "$LED" "$SID" 2>&1)
if [ "$open_stage" != "1" ]; then
  echo "== $(ts) REFUSED: stage [$SID] is not open in the ledger ($open_stage); SIGTERM to $U so that the run stays resumable"
  systemctl stop "$U"
  exit 3
fi
while :; do
  if ! systemctl is-active --quiet "$U"; then
    echo "== $(ts) $U is no longer active before the target: $(count); nothing sent to it"
    exit 0
  fi
  read -r n states <<< "$(count)"
  if [ "${n:-0}" -ge "$TARGET" ]; then
    echo "== $(ts) $n reservations $states: SIGTERM (systemctl stop $U)"
    systemctl stop "$U"
    echo "== $(ts) unit after the stop: $(systemctl show -p ActiveState -p Result -p ExecMainStatus --value "$U" | tr '\n' ' ')"
    sleep 2
    echo "== $(ts) the stage's ledger rows now: $(count)"
    exit 0
  fi
  sleep 1
done
