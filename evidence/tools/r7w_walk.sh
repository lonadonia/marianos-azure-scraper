#!/usr/bin/env bash
# PRIVATE (workstation): the recorded walkthrough slice R7w of the run R7 (ops6/stage_defs.json, key R7w).
#   r7w_walk.sh RUN_ID
# 1. the stage's ceiling fitted to what the envelope holds (fit_stage.py), stage_defs.json installed on the VM and
#    checked there;
# 2. the stage opened in the ledger and its ceiling set in the collector, nothing started (NO_START=1);
# 3. the steps file written (make_walk_steps6.py: SIGTERM after 12 pages, the slice stopper at the stage's target,
#    the named UPCs for the trace step), installed beside the recorder on the VM and checked there;
# 4. record_cast.py started on the VM as the transient unit marianos-walk-r7w (it survives a lost SSH session),
#    recording into ops-rc6/walk/ (walkthrough_r7w.cast, raw_r7w/). Every paid command in the steps goes through
#    the gated harness (mstage6) and the stage's ceiling.
# Follow it: follow_slice.sh M-R7w-walkthrough-110rc6-20261117 marianos-walk-r7w. When it has ended:
# after_slice6.sh R7w marianos-stage-r7w,marianos-stage-r7w-2 RUN R7w 'OUTCOME' PREVIOUS_R7_FOLDERS..., then the
# rendering (render_cast.py on the VM, with no collector unit running).
set -euo pipefail
cd [redacted:workstation-path]
RUN="$1"
[[ "$RUN" =~ ^[0-9A-Z]{26}$ ]] || { echo "bad run id"; exit 2; }
KEY=R7w
UNIT=marianos-stage-r7w
WALK=/var/lib/marianos-collector/ops-rc6/walk
[ ! -e "logs/rc6/walk_steps_r7w.json" ] || { echo "REFUSED: logs/rc6/walk_steps_r7w.json exists"; exit 2; }
bash tools/vm.sh "sudo test ! -e $WALK/walkthrough_r7w.cast && sudo test ! -e $WALK/raw_r7w" \
  || { echo "REFUSED: a recording of R7w already exists on the VM"; exit 2; }
bash tools/vm.sh "sudo mstage6 ledger-status" > "logs/rc6/ledger_before_$KEY.json"
python -I ops6/fit_stage.py "$KEY" "logs/rc6/ledger_before_$KEY.json" | tr -d '\r'
tar -cf - -C ops6 stage_defs.json | VM_STDIN=1 bash tools/vm.sh "T=\$(mktemp -d) && tar -xf - -C \$T && sudo install -o root -g marianos -m 0640 \$T/stage_defs.json /var/lib/marianos-collector/ops-rc6/stage_defs.json && rm -rf \$T"
L=$(sha256sum ops6/stage_defs.json | cut -c1-64)
R=$(bash tools/vm.sh "sudo sha256sum /var/lib/marianos-collector/ops-rc6/stage_defs.json" | cut -c1-64)
[ "$L" = "$R" ] || { echo "REFUSED: the VM's stage_defs.json ($R) is not the workstation's ($L)"; exit 2; }
read -r SUBS TARGET SID < <(python -I -c "import json,sys; s=json.load(open('ops6/stage_defs.json',encoding='utf-8'))['stages'][sys.argv[1]]; print(s['max_submissions'], s.get('slice_target') or 0, s['stage_id'])" "$KEY" | tr -d '\r')
[[ "$SID" =~ ^M-[A-Za-z0-9-]+$ ]] || { echo "bad stage id"; exit 2; }
[[ "$SUBS" =~ ^[0-9]+$ && "$TARGET" =~ ^[0-9]+$ && "$TARGET" -gt 0 && "$TARGET" -lt "$SUBS" ]] \
  || { echo "bad ceiling or target"; exit 2; }
RUNARGS=$(python -I -c "import json,sys; print(json.load(open('ops6/stage_defs.json',encoding='utf-8'))['stages'][sys.argv[1]]['command'])" "$KEY" | tr -d '\r')
echo "walkthrough slice $KEY ($SID): ceiling $SUBS, target $TARGET, units $UNIT and $UNIT-2, run $RUN"
NO_START=1 bash ops6/launch_stage6.sh "$KEY" "$UNIT" "$SUBS" "$RUNARGS"
python -I ops6/make_walk_steps6.py logs/rc6/walk_steps_r7w.json "$SID" "$RUN" "$UNIT" 12 "$TARGET" \
  0084024314377 0001280052496 0001780014939 0001780014941 0002310014848 0003980014995 | tr -d '\r'
tar -cf - -C logs/rc6 walk_steps_r7w.json | VM_STDIN=1 bash tools/vm.sh "T=\$(mktemp -d) && tar -xf - -C \$T && sudo install -o root -g root -m 0644 \$T/walk_steps_r7w.json $WALK/steps_r7w.json && rm -rf \$T"
L=$(sha256sum logs/rc6/walk_steps_r7w.json | cut -c1-64)
R=$(bash tools/vm.sh "sudo sha256sum $WALK/steps_r7w.json" | cut -c1-64)
[ "$L" = "$R" ] || { echo "REFUSED: the VM's steps file ($R) is not the workstation's ($L)"; exit 2; }
bash tools/vm.sh "sudo systemd-run --quiet --unit=marianos-walk-r7w --working-directory=$WALK /usr/bin/python3 -I $WALK/tools/record_cast.py $WALK/steps_r7w.json $WALK/walkthrough_r7w.cast $WALK/raw_r7w && sleep 3 && echo \"recorder: \$(systemctl is-active marianos-walk-r7w)\""
date -u +%Y-%m-%dT%H:%M:%SZ
