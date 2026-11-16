#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root), for the recorded walkthrough: starts one gated execution as the transient unit UNIT
# (`mstage --unit UNIT run STAGE_ID -- ARGS...`) with the operator's watcher beside it, prints the unit's journal
# (the collector's JSON lines) from its start until the unit is no longer active, then prints the unit's exit status
# and ends with it.
# Usage: [DB=name] run_and_follow.sh UNIT STAGE_ID ARGS...
set -u
U="$1"; SID="$2"; shift 2
[[ "$U" =~ ^marianos-stage-[a-z0-9-]+$ ]] || { echo "bad unit name"; exit 2; }
DB="${DB:-$(sed -n 's#^MARIANOS_COLLECTOR_DATABASE_URL=postgresql://[^/]*/\([^?]*\).*#\1#p' /etc/marianos-collector/collector.env)}"
since=$(date '+%Y-%m-%d %H:%M:%S')
mstage --unit "$U" run "$SID" -- "$@" || exit $?
# the operator's watcher beside it (its log is not part of the recording)
systemd-run --quiet --unit="${U/marianos-stage-/marianos-watch-}" /var/lib/marianos-collector/ops111/watch_stage.sh \
  "$U" "$SID" "$DB" "/var/lib/marianos-collector/ops111/stages/$SID/watch_$U.log"
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
