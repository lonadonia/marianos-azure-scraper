#!/usr/bin/env bash
# PRIVATE (workstation): starts one stage on the owner VM through stage_launch.sh. Refuses while any collector or
# stage unit is active. The submission ceiling SUBS sets both the collector's ceiling and (through prep_stage.py's
# definition) the ledger stage; USD = SUBS x 0.0015.
#   [NO_START=1] launch_stage.sh KEY UNIT SUBS 'RUNARGS' ['PRE_CLI'] [DB]   (NO_START: open the stage, start nothing)
set -euo pipefail
cd [redacted:workstation-path]
KEY="$1"; UNIT="$2"; SUBS="$3"; RUNARGS="$4"; PRE_CLI="${5:-}"; DB="${6:-}"
[[ "$UNIT" =~ ^marianos-stage-[a-z0-9-]+$ ]] || { echo "bad unit name"; exit 2; }
USD=$(python -I -c "import sys; print(f'{int(sys.argv[1]) * 0.0015:.6f}')" "$SUBS")
DEF_SUBS=$(python -I -c "import json,sys; print(json.load(open('ops6/stage_defs.json',encoding='utf-8'))['stages'][sys.argv[1]]['max_submissions'])" "$KEY")
[ "$DEF_SUBS" = "$SUBS" ] || { echo "REFUSED: $KEY's definition says $DEF_SUBS submissions, not $SUBS"; exit 2; }
SID=$(python -I -c "import json,sys; print(json.load(open('ops6/stage_defs.json',encoding='utf-8'))['stages'][sys.argv[1]]['stage_id'])" "$KEY")
bash tools/vm.sh 'n=$(systemctl list-units --no-legend --state=active "marianos-stage-*" "marianos-watch-*" | wc -l); [ "$n" -eq 0 ] || { systemctl list-units --no-legend "marianos-*"; echo "REFUSED: a stage or watcher unit is active"; exit 3; }'
date -u +%Y-%m-%dT%H:%M:%SZ
REASON="$KEY ($SID): $SUBS submissions, USD $USD, within the Marianos envelope of the campaign oxylabs-marianos-20261116 (new credential); authorized by Hamza on 16 November 2026 (closeout brief)"
VM_STDIN=1 bash tools/vm.sh "sudo env STAGE_KEY=$KEY UNIT=$UNIT SUBS=$SUBS USD=$USD RUNARGS='$RUNARGS' REASON='$REASON' PRE_CLI='$PRE_CLI' ${DB:+DB=$DB} ${NO_START:+NO_START=1} bash -s" < ops6/stage_launch.sh
