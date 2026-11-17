#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root), for the recorded walkthrough of 1.10.0rc6: starts one gated execution as the transient
# unit UNIT (`mstage6 --unit UNIT run STAGE_ID -- ARGS...`) with the operator's watcher beside it and, when
# SLICE_TARGET is set, the slice stopper (SIGTERM once the stage holds that many reservations in the ledger: a
# resumable stop). Prints the unit's journal (the collector's JSON lines) from its start until the unit is no longer
# active, then the unit's exit status, and ends with it.
# Usage: [DB=name] [SLICE_TARGET=n] run_and_follow6.sh UNIT STAGE_ID ARGS...
set -u
OPS=/var/lib/marianos-collector/ops-rc6
U="$1"; SID="$2"; shift 2
[[ "$U" =~ ^marianos-stage-[a-z0-9-]+$ ]] || { echo "bad unit name"; exit 2; }
[[ "$SID" =~ ^M-[A-Za-z0-9-]+$ ]] || { echo "bad stage id"; exit 2; }
DB="${DB:-$(sed -n 's#^MARIANOS_COLLECTOR_DATABASE_URL=postgresql://[^/]*/\([^?]*\).*#\1#p' /etc/marianos-collector/collector.env)}"
since=$(date '+%Y-%m-%d %H:%M:%S')
mstage6 --unit "$U" run "$SID" -- "$@" || exit $?
# the operator's watcher and, for a slice, the slice stopper beside it (their logs are not part of the recording)
systemd-run --quiet --unit="${U/marianos-stage-/marianos-watch-}" "$OPS/watch_stage.sh" \
  "$U" "$SID" "$DB" "$OPS/stages/$SID/watch_$U.log"
if [ -n "${SLICE_TARGET:-}" ]; then
  systemd-run --quiet --unit="${U/marianos-stage-/marianos-slicestop-}" "$OPS/slice_stop.sh" \
    "$U" "$SID" "$SLICE_TARGET" "$OPS/stages/$SID/slice_stop_$U.log"
fi
journalctl -f -u "$U" -o cat --since "$since" &
J=$!
sleep 2
while systemctl is-active --quiet "$U"; do sleep 1; done
sleep 2
kill "$J" 2>/dev/null
wait "$J" 2>/dev/null
code=$(systemctl show -p ExecMainStatus --value "$U" 2>/dev/null)
code="${code:-0}"
echo "{\"event\": \"UNIT_ENDED\", \"message\": \"$U ended with exit status $code\"}"
systemctl reset-failed "$U" 2>/dev/null
exit "$code"
