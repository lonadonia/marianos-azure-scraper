#!/usr/bin/env bash
# PRIVATE (workstation): after a stage's unit has ended. Collects the stage's evidence on the owner VM, closes the
# stage in the shared trial ledger with OUTCOME, pulls the evidence folder and checks its SHA256SUMS, then analyses
# it. Refuses while the stage's unit is active. No provider request.
#   [SKIP_STORED=1] stage_end.sh KEY UNIT[,UNIT2...] RUN_ID EVNAME 'OUTCOME' [DB] [DATA]
# OUTCOME is one line without apostrophes. DB and DATA name an isolated target (the publication tests).
set -euo pipefail
cd [redacted:workstation-path]
KEY="$1"; UNIT="$2"; RUN="$3"; EVN="$4"; OUTCOME="$5"; DB="${6:-}"; DATA="${7:-}"
for u in ${UNIT//,/ }; do [[ "$u" =~ ^marianos-stage-[a-z0-9-]+$ ]] || { echo "bad unit name $u"; exit 2; }; done
UNITS="${UNIT//,/ }"; UNIT="${UNITS##* }"  # several units (comma-separated): all must have ended; the last one is checked and watched
[[ "$RUN" =~ ^[0-9A-Z]{26}$ ]] || { echo "bad run id"; exit 2; }
[[ "$EVN" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "bad evidence name"; exit 2; }
case "$OUTCOME" in *"'"*) echo "OUTCOME must not hold an apostrophe"; exit 2 ;; esac
SID=$(python -I -c "import json,sys; print(json.load(open('ops6/stage_defs.json',encoding='utf-8'))['stages'][sys.argv[1]]['stage_id'])" "$KEY")
WATCH="${UNIT/marianos-stage-/marianos-watch-}"
for u in $UNITS; do bash tools/vm.sh "s=\$(systemctl is-active $u 2>/dev/null || true); case \"\$s\" in active|activating|deactivating|reloading) echo \"REFUSED: $u is \$s\"; exit 3;; esac; echo \"$u: \${s:-gone}; $WATCH: \$(systemctl is-active $WATCH 2>/dev/null || true)\""; done
OUT="/var/lib/marianos-collector/ops-rc6/evidence/$EVN"
bash tools/vm.sh "[ ! -e '$OUT' ] || { echo 'REFUSED: $OUT exists'; exit 4; }; sudo env UNIT='$UNITS' ${SKIP_STORED:+SKIP_STORED=1} ${DB:+DB=$DB} ${DATA:+DATA=$DATA} /var/lib/marianos-collector/ops-rc6/stage_evidence6.sh '$SID' '$RUN' '$OUT'" | tail -22
bash tools/vm.sh "sudo mstage6 close-stage '$SID' '$OUTCOME'"
bash tools/vm.sh "sudo mstage6 ledger-status" > "logs/rc6/ledger_after_$EVN.json"
python -I -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); m=d['projects']['marianos']; print('ledger after', sys.argv[2], 'chain', d['chain'], 'lease', d['active_lease'], 'committed', d['committed_usd'], 'marianos spendable', m['spendable_in_envelope_usd'], 'unknown rows', m['unknown_rows'])" "logs/rc6/ledger_after_$EVN.json" "$EVN"
bash tools/pull_dir.sh "$OUT" ev
python -I ops/analyze_stage.py "ev/$EVN" | tail -45
