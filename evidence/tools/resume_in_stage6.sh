#!/usr/bin/env bash
# PRIVATE (workstation): resumes the run R7 as one more unit of a slice whose stage is still open, after the watcher's
# repeat rule stopped that slice's previous unit (a resumable stop, exit 75). One stage, one ledger record, one
# ceiling and one slice target for all its units; the evidence is collected once, at the slice's end
# (after_slice6.sh KEY UNIT1,UNIT2,... RUN EVN 'OUTCOME' ...).
# Starts on the VM, as root: the gated execution (mstage6 --unit UNIT run STAGE_ID -- <the stage's command>), the
# operator's watcher beside it (stages/<SID>/watch_<UNIT>.log) and the slice stopper at the stage's slice target
# (stages/<SID>/slice_stop_<UNIT>.log). Refuses when a collector unit is active or the unit name has been used; the
# ledger refuses every reservation of a stage that is not open (the unit then ends at once, and this script says so).
#   resume_in_stage6.sh KEY UNIT
set -euo pipefail
cd [redacted:workstation-path]
KEY="$1"; U="$2"
[[ "$U" =~ ^marianos-stage-[a-z0-9-]+$ ]] || { echo "bad unit name"; exit 2; }
read -r SID TARGET RUNARGS < <(python -I -c "import json,sys; s=json.load(open('ops6/stage_defs.json',encoding='utf-8'))['stages'][sys.argv[1]]; print(s['stage_id'], s.get('slice_target') or 0, s['command'])" "$KEY" | tr -d '\r')
[[ "$SID" =~ ^M-[A-Za-z0-9-]+$ ]] || { echo "bad stage id"; exit 2; }
[[ "$TARGET" =~ ^[0-9]+$ && "$TARGET" -gt 0 ]] || { echo "bad slice target"; exit 2; }
[[ "$RUNARGS" =~ ^resume\ --store\ marianos-[0-9]+-[a-z]+$ ]] || { echo "bad stage command: $RUNARGS"; exit 2; }
W="${U/marianos-stage-/marianos-watch-}"; S="${U/marianos-stage-/marianos-slicestop-}"
OPS=/var/lib/marianos-collector/ops-rc6
echo "== $(date -u +%FT%TZ) resume in stage $SID as $U (slice target $TARGET)"
bash tools/vm.sh "set -e
a=\$(systemctl list-units --no-legend --state=active,activating,deactivating 'marianos-stage-*' | wc -l)
[ \"\$a\" -eq 0 ] || { echo \"REFUSED: \$a collector unit(s) active\"; systemctl list-units --no-legend 'marianos-stage-*'; exit 3; }
for x in $U $W $S; do
  st=\$(systemctl show \$x -p LoadState --value 2>/dev/null || true)
  [ \"\$st\" = not-found ] || { echo \"REFUSED: unit \$x exists (\$st): another name\"; exit 3; }
done
sudo test -d $OPS/stages/$SID || { echo 'REFUSED: no stage folder for $SID'; exit 3; }
DB=\$(sudo sed -n 's#^MARIANOS_COLLECTOR_DATABASE_URL=postgresql://[^/]*/\\([^?]*\\).*#\\1#p' /etc/marianos-collector/collector.env)
[ -n \"\$DB\" ] || { echo 'REFUSED: no database name'; exit 3; }
sudo mstage6 --unit $U run $SID -- $RUNARGS
sleep 5
echo \"$U: \$(systemctl is-active $U || true)\"
sudo systemd-run --quiet --unit=$W $OPS/watch_stage.sh $U $SID \$DB $OPS/stages/$SID/watch_$U.log
sudo systemd-run --quiet --unit=$S $OPS/slice_stop.sh $U $SID $TARGET $OPS/stages/$SID/slice_stop_$U.log
sleep 2
echo \"watcher: \$(systemctl is-active $W || true); slice stopper: \$(systemctl is-active $S || true)\"
systemctl is-active --quiet $U || { echo 'the unit is not active: see its journal'; sudo journalctl -u $U -o cat --no-pager | tail -5 | cut -c1-300; exit 4; }
" | tr -d '\r'
echo "== $(date -u +%FT%TZ) started"
