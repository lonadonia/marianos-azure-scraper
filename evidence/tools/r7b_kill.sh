#!/usr/bin/env bash
# PRIVATE (workstation): slice R7b with the operator's hard-kill check. Starts the slice (resume of R7) with no slice
# stopper beside its first unit, then kill_recover.sh as a transient unit on the VM: SIGKILL of every process of
# marianos-stage-r7b once its journal shows 40 pages collected (both lanes working), the dead ledger lease left to
# expire, the same run resumed in the same open stage as marianos-stage-r7b2, with the slice stopper (600
# reservations in the stage, the killed execution's included) beside it.
set -euo pipefail
cd [redacted:workstation-path]
SID=M-R7b-full-run-110rc6-20261117
# K: pages collected in the first unit's journal before its SIGKILL (40 planned; lowered when the repeat rule would stop
# the slice first: R7a was stopped at 27 collected pages)
K="${K:-40}"
[[ "$K" =~ ^[0-9]+$ ]] && [ "$K" -ge 5 ] || { echo "bad K"; exit 2; }
bash ops6/launch_stage6.sh R7b marianos-stage-r7b 610 'resume --store marianos-53100502-pickup'
bash tools/vm.sh "sudo systemd-run --quiet --unit=marianos-killrecover-r7b /var/lib/marianos-collector/ops-rc6/kill_recover.sh marianos-stage-r7b marianos-stage-r7b2 $SID $K marianos_rc5 /var/lib/marianos-collector/ops-rc6/stages/$SID/kill_recover.log 600 && echo \"kill_recover: \$(systemctl is-active marianos-killrecover-r7b)\""
date -u +%Y-%m-%dT%H:%M:%SZ
