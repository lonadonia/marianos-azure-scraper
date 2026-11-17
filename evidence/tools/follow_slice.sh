#!/usr/bin/env bash
# PRIVATE (workstation): follows one slice for the operator. Every 60 s reads the stage watcher's latest lines on the
# VM; prints a progress line every 5 minutes, and at once any operator stop, a unit no longer active, or a failed
# read. Ends (exit 0) when no unit of the slice is active and the watcher has ended. No provider request.
#   follow_slice.sh STAGE_ID UNIT[,UNIT2...]
set -u
cd [redacted:workstation-path]
SID="$1"; UNITS="${2//,/ }"
[[ "$SID" =~ ^M-[A-Za-z0-9-]+$ ]] || { echo "bad stage id"; exit 2; }
LOG=/var/lib/marianos-collector/ops-rc6/stages/$SID/watch.log
last=0; seen_stop=""
while :; do
  out=$(timeout 90 bash tools/vm.sh "sudo tail -n 3 \$(sudo sh -c 'ls -t $(dirname $LOG)/watch*.log 2>/dev/null | head -1') 2>/dev/null; for u in $UNITS; do printf 'UNIT %s %s\n' \$u \$(systemctl is-active \$u 2>/dev/null || true); done; printf 'WATCH %s\n' \$(systemctl list-units --no-legend --state=active 'marianos-watch-*' 'marianos-slicestop-*' 'marianos-killrecover-*' | wc -l)" 2>&1) || { echo "$(date -u +%H:%M:%SZ) read failed: $(echo "$out" | tail -1 | cut -c1-160)"; sleep 60; continue; }
  now=$(date +%s)
  stop=$(echo "$out" | grep -E "OPERATOR STOP|watch ends|REFUSED|stopper" | tail -1)
  if [ -n "$stop" ] && [ "$stop" != "$seen_stop" ]; then echo "$(date -u +%H:%M:%SZ) $(echo "$stop" | cut -c1-400)"; seen_stop="$stop"; fi
  if [ $((now - last)) -ge 300 ]; then
    p=$(echo "$out" | grep -E "pages=" | tail -1 | sed -E 's/.*(unit=[^ ]+ run=[^ ]+ status=[^ ]+ pages=\[[^]]*\] distinct_upcs=[^ ]+ deferred[^ ]* page2plus_slice[^ ]* ledger=.*)/\1/' | cut -c1-420)
    echo "$(date -u +%H:%M:%SZ) ${p:-no progress line yet}"
    last=$now
  fi
  active=$(echo "$out" | grep -E "^UNIT " | grep -c -E " (active|activating|deactivating)$")
  helpers=$(echo "$out" | grep -E "^WATCH " | awk '{print $NF}')
  if [ "$active" -eq 0 ] && [ "${helpers:-1}" = "0" ]; then
    echo "$(date -u +%H:%M:%SZ) SLICE ENDED: no unit of the slice and no watcher, slice stopper or kill-recover unit active"
    echo "$out" | grep -E "pages=|OPERATOR|watch ends" | tail -2 | cut -c1-420
    exit 0
  fi
  sleep 60
done
