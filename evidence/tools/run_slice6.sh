#!/usr/bin/env bash
# PRIVATE (workstation): one slice of the 1.10.0rc6 live work. Reads the stage's definition (ops6/stage_defs.json),
# launches it through launch_stage6.sh (the collector's ceiling, the ledger stage, the run unit and its watcher) and,
# when the definition has a slice_target, starts slice_stop.sh beside the unit as a transient unit (SIGTERM once the
# stage holds that many reservations in the ledger: a resumable stop before the ceiling).
#   run_slice6.sh KEY UNIT
set -euo pipefail
cd [redacted:workstation-path]
KEY="$1"; UNIT="$2"
# The ceiling fitted to what is left in the envelope (the ledger refuses a stage beyond it; a slice must end with
# SIGTERM before its ceiling), then the definitions installed on the VM and checked there.
bash tools/vm.sh "sudo mstage6 ledger-status" > "logs/rc6/ledger_before_$KEY.json"
python -I ops6/fit_stage.py "$KEY" "logs/rc6/ledger_before_$KEY.json" | tr -d '\r'
tar -cf - -C ops6 stage_defs.json | VM_STDIN=1 bash tools/vm.sh "T=\$(mktemp -d) && tar -xf - -C \$T && sudo install -o root -g marianos -m 0640 \$T/stage_defs.json /var/lib/marianos-collector/ops-rc6/stage_defs.json && rm -rf \$T"
L=$(sha256sum ops6/stage_defs.json | cut -c1-64)
R=$(bash tools/vm.sh "sudo sha256sum /var/lib/marianos-collector/ops-rc6/stage_defs.json" | cut -c1-64)
[ "$L" = "$R" ] || { echo "REFUSED: the VM's stage_defs.json ($R) is not the workstation's ($L)"; exit 2; }
# Windows Python ends its lines with CR LF; read keeps the CR on its last field (on 2026-11-16 the stage id reached
# slice_stop.sh as 'M-R6a-...\r', so the stopper counted no reservation), hence tr -d and the checks below.
read -r SUBS TARGET SID < <(python -I -c "import json,sys; s=json.load(open('ops6/stage_defs.json',encoding='utf-8'))['stages'][sys.argv[1]]; print(s['max_submissions'], s.get('slice_target') or 0, s['stage_id'])" "$KEY" | tr -d '\r')
[[ "$SID" =~ ^M-[A-Za-z0-9-]+$ ]] || { echo "bad stage id"; exit 2; }
[[ "$SUBS" =~ ^[0-9]+$ && "$TARGET" =~ ^[0-9]+$ ]] || { echo "bad ceiling or target"; exit 2; }
RUNARGS=$(python -I -c "import json,sys; print(json.load(open('ops6/stage_defs.json',encoding='utf-8'))['stages'][sys.argv[1]]['command'])" "$KEY" | tr -d '\r')
# An isolated target named by the definition ("target": its own database and data folder) and commands without a
# provider request run on it before the stage ("pre_cli", e.g. "db-upgrade;sync-config"); none for R7's slices.
read -r PRE TDB < <(python -I -c "import json,re,sys; s=json.load(open('ops6/stage_defs.json',encoding='utf-8'))['stages'][sys.argv[1]]; t=(s.get('target') or {}).get('database_url',''); m=re.search(r'/([a-z0-9_]+)[?]', t); print(s.get('pre_cli') or '-', m.group(1) if m else '-')" "$KEY" | tr -d '\r')
[ "$PRE" = "-" ] && PRE=""
[ "$TDB" = "-" ] && TDB=""
PRE_RE='^[a-z;-]+$'
[[ -z "$PRE" || "$PRE" =~ $PRE_RE ]] || { echo "bad pre_cli"; exit 2; }
[[ -z "$TDB" || "$TDB" =~ ^[a-z0-9_]+$ ]] || { echo "bad target database"; exit 2; }
echo "slice $KEY ($SID): ceiling $SUBS, target $TARGET, unit $UNIT${TDB:+, isolated target $TDB}${PRE:+, before the stage: $PRE}"
bash ops6/launch_stage6.sh "$KEY" "$UNIT" "$SUBS" "$RUNARGS" "$PRE" "$TDB"
if [ "$TARGET" -gt 0 ]; then
  STOPU="${UNIT/marianos-stage-/marianos-slicestop-}"
  bash tools/vm.sh "sudo systemd-run --quiet --unit=$STOPU /var/lib/marianos-collector/ops-rc6/slice_stop.sh $UNIT $SID $TARGET /var/lib/marianos-collector/ops-rc6/stages/$SID/slice_stop.log && echo \"slice stopper: \$(systemctl is-active $STOPU)\""
fi
date -u +%Y-%m-%dT%H:%M:%SZ
