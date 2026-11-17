#!/usr/bin/env bash
# PRIVATE (workstation): 1.10.0rc6's own check that an incomplete run cannot replace a published dataset, offline, on
# a COPY of 1.10.0rc5's isolated publication target marianos_pubtest5 (where P4 is published, after P6's publication
# and its rollback, and P5 is a partial dataset stopped at its ceiling). No provider request: the copy holds no
# credential, and rc5's target is only read (pg_dump; its data folder copied). Output in logs/rc6/protect6/.
#   1. the copy made (vm_copy_target6.sh with SRC_DB/SRC_DATA); 2. db-upgrade on the copy (1.10.0rc6's schema);
#   3. the published state; 4. publish --run P5 with 1.10.0rc6: refused (exit 6, the refusal in its output);
#   5. the published state again: equal in every section; 6. the copy dropped.
set -euo pipefail
cd [redacted:workstation-path]
P5=01M7JSXE192AD3KH2SV0178F4A
SRC_DB=marianos_pubtest5
SRC_DATA=/var/lib/marianos-collector/pubtest5/data
CN="${CN:-pt5c}"
L="${L:-logs/rc6/protect6}"
[ ! -e "$L" ] || { echo "REFUSED: $L exists"; exit 2; }
mkdir -p "$L"
copy() { VM_STDIN=1 bash tools/vm.sh "sudo env COPY=$CN SRC_DB=$SRC_DB SRC_DATA=$SRC_DATA $* bash -s" < ops6/vm_copy_target6.sh 2>&1 | tr -d '\r'; }
state() {
  bash tools/vm.sh "sudo /var/lib/marianos-collector/ops111/pub_state.sh marianos_$CN /var/lib/marianos-collector/ops-rc6/$CN/data marianos-53100502-pickup" \
    | tr -d '\r' > "$L/pub_state_$1.txt"
  echo "  pub_state_$1.txt: $(wc -l < "$L/pub_state_$1.txt") lines"
}
ALL=(pointer publications "every file under published/" latest.json "exports of the published run")
{
  echo "== $(date -u +%FT%TZ) 1.10.0rc6 refuses an incomplete run beside a published dataset (a copy of $SRC_DB)"
  copy MODE=make
  { echo "$(date -u +%FT%TZ) db-upgrade"; copy MODE=cmd "ARGS='db-upgrade'"; } > "$L/1_db_upgrade.log"
  echo "  db-upgrade: $(tail -1 "$L/1_db_upgrade.log")"
  state 0_before_P5_publish
  { echo "$(date -u +%FT%TZ) publish --run $P5"; copy MODE=cmd "ARGS='publish --run $P5'"; } > "$L/2_P5_publish_refused.log"
  if grep -q '"event": "COMMAND_REFUSED"' "$L/2_P5_publish_refused.log" && grep -q '"exit_code": 6' "$L/2_P5_publish_refused.log" \
     && [ "$(tail -1 "$L/2_P5_publish_refused.log")" = "exit 6" ]; then
    echo "  CHECK PASSED: P5 refused by 1.10.0rc6 (exit 6), the refusal in its output"
  else
    echo "  CHECK FAILED: P5 was not refused as expected: $(tail -1 "$L/2_P5_publish_refused.log")"
  fi
  state 1_after_P5_refusal
  python -I ops/pub_compare.py "$(cygpath -m "$L/pub_state_0_before_P5_publish.txt")" \
    "$(cygpath -m "$L/pub_state_1_after_P5_refusal.txt")" --expect-equal "${ALL[@]}" | tr -d '\r' > "$L/COMPARE_before_vs_after_P5_refusal.txt" || true
  echo "  COMPARE: $(tail -1 "$L/COMPARE_before_vs_after_P5_refusal.txt")"
  grep -q "^== pointer" "$L/pub_state_0_before_P5_publish.txt" && sed -n '/^== pointer/,/^== publications/p' "$L/pub_state_0_before_P5_publish.txt" | sed -n 2p | cut -c1-200
  copy MODE=drop
  echo "== $(date -u +%FT%TZ) done"
} 2>&1 | tee "$L/PROTECT6.log"
