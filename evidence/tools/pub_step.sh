#!/usr/bin/env bash
# PRIVATE (workstation): one step of the publication test on the isolated target marianos_pubtest5 (P4 to P6), no
# provider request. Every step's output goes to logs/pub5/ with the command's exit code as its last line.
#   pub_step.sh state LABEL              the published state (pub_state.sh) -> pub_state_LABEL.txt
#   pub_step.sh publish KEY RUN NAME     publish --run RUN through stage KEY's target -> NAME.log
#   pub_step.sh rollback KEY NAME        rollback-publication through stage KEY's target -> NAME.log
#   pub_step.sh status KEY RUN NAME      status --run RUN -> NAME.log
set -euo pipefail
cd /c/m8
mkdir -p logs/pub5
DB=marianos_pubtest5
DATA=/var/lib/marianos-collector/pubtest5/data
STORE=marianos-53100502-pickup
sid() { python -I -c "import json,sys; print(json.load(open('ops/stage_defs.json',encoding='utf-8'))['stages'][sys.argv[1]]['stage_id'])" "$1"; }
case "$1" in
  state)
    [[ "$2" =~ ^[0-9A-Za-z_]+$ ]] || { echo "bad label"; exit 2; }
    bash tools/vm.sh "sudo /var/lib/marianos-collector/ops111/pub_state.sh $DB $DATA $STORE" > "logs/pub5/pub_state_$2.txt"
    echo "logs/pub5/pub_state_$2.txt: $(wc -l < "logs/pub5/pub_state_$2.txt") lines" ;;
  publish)
    S=$(sid "$2"); [[ "$3" =~ ^[0-9A-Z]{26}$ ]] || { echo "bad run id"; exit 2; }
    bash tools/vm.sh "sudo mstage cli $S -- publish --run $3; echo \"exit \$?\"" > "logs/pub5/$4.log" 2>&1 || true
    tail -1 "logs/pub5/$4.log" ;;
  rollback)
    S=$(sid "$2")
    bash tools/vm.sh "sudo mstage cli $S -- rollback-publication --store $STORE --reason 'P6: rollback test on the isolated target, back to P4'; echo \"exit \$?\"" > "logs/pub5/$3.log" 2>&1 || true
    tail -1 "logs/pub5/$3.log" ;;
  status)
    S=$(sid "$2"); [[ "$3" =~ ^[0-9A-Z]{26}$ ]] || { echo "bad run id"; exit 2; }
    bash tools/vm.sh "sudo mstage cli $S -- status --run $3; echo \"exit \$?\"" > "logs/pub5/$4.log" 2>&1 || true
    tail -1 "logs/pub5/$4.log" ;;
  *) echo "usage: see the header"; exit 2 ;;
esac
