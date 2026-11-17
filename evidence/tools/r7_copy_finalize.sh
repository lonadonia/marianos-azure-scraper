#!/usr/bin/env bash
# PRIVATE (workstation): when the envelope ends before R7 completes, R7 itself stays resumable on the run target (a
# funded continuation resumes it), and its state at the end of its last slice is finalized in an ISOLATED COPY of the
# target instead, with no provider request: the copy's database restored from a fresh dump of the target's, its own
# data folder, no credential (vm_copy_target6.sh). On the copy: status; stop; finalize (checks, gates, exports);
# publish, which must refuse a partial dataset (exit 6, the refusal in its output); status. Then the copy's evidence
# (stage_evidence6.sh with COPY_ENV) pulled to ev/R7fin_copy like a slice's, and the copy dropped once the pulled
# files match the VM's. The run target is only read; R7 is checked unchanged on it before and after (status).
#   r7_copy_finalize.sh RUN_ID LAST_STAGE_ID
set -euo pipefail
cd [redacted:workstation-path]
RUN="$1"; SID="$2"
[[ "$RUN" =~ ^[0-9A-Z]{26}$ ]] || { echo "bad run id"; exit 2; }
[[ "$SID" =~ ^M-[A-Za-z0-9-]+$ ]] || { echo "bad stage id"; exit 2; }
EVN="${EVN:-R7fin_copy}"   # another name only for a test
L="logs/rc6/$EVN.log"
OUT=/var/lib/marianos-collector/ops-rc6/evidence/$EVN
CN="${CN:-r7fin}"
C=/var/lib/marianos-collector/ops-rc6/$CN
[ ! -e "$L" ] || { echo "REFUSED: $L exists"; exit 2; }
[ ! -e "ev/$EVN" ] || { echo "REFUSED: ev/$EVN exists"; exit 2; }
copy() { VM_STDIN=1 bash tools/vm.sh "sudo env COPY=$CN $* bash -s" < ops6/vm_copy_target6.sh 2>&1 | tr -d '\r'; }
oncopy() {  # NAME ARGS [REASON]
  local n="$1" a="$2" r="${3:-}"
  { echo "$(date -u +%FT%TZ) on the copy: $a"; copy MODE=cmd "ARGS='$a'" ${r:+"REASON='$r'"}; } > "logs/rc6/${EVN}_$n.log"
  echo "  $n: $(tail -1 "logs/rc6/${EVN}_$n.log")"
}
real_status() { bash tools/vm.sh "sudo marianos status --run $RUN; echo \"exit \$?\"" 2>&1 | tr -d '\r' > "logs/rc6/${EVN}_target_status_$1.log"; }
{
  echo "== $(date -u +%FT%TZ) R7 ($RUN) finalized in an isolated copy; R7 left resumable on the run target"
  busy=$(bash tools/vm.sh "systemctl list-units 'marianos-*' --state=active,activating,deactivating --no-legend --plain | wc -l" | tr -d '\r')
  [ "$busy" = "0" ] || { echo "REFUSED: $busy marianos unit(s) active"; exit 2; }
  real_status before; echo "  target status before: $(tail -1 "logs/rc6/${EVN}_target_status_before.log")"
  copy MODE=make
  oncopy 1_status_before "status --run $RUN"
  oncopy 2_stop "stop --run $RUN" "R7 is left resumable on the run target; this isolated copy finalizes its state at the end of its last slice (no provider request)"
  oncopy 3_finalize "finalize --run $RUN"
  oncopy 4_publish "publish --run $RUN"
  if grep -q '"event": "COMMAND_REFUSED"' "logs/rc6/${EVN}_4_publish.log" && grep -q '"exit_code": 6' "logs/rc6/${EVN}_4_publish.log" \
     && [ "$(tail -1 "logs/rc6/${EVN}_4_publish.log")" = "exit 6" ]; then
    echo "  CHECK PASSED: the copy's partial dataset refused (exit 6), the refusal in its output"
  else
    echo "  NOTE: publish on the copy did not refuse with exit 6: $(tail -1 "logs/rc6/${EVN}_4_publish.log") (read the log)"
  fi
  oncopy 5_status_after "status --run $RUN"
  echo "== $(date -u +%FT%TZ) the copy's evidence"
  bash tools/vm.sh "sudo test ! -e $OUT && sudo env UNIT='' COPY_ENV=$C/collector.env DB=marianos_$CN DATA=$C/data /var/lib/marianos-collector/ops-rc6/stage_evidence6.sh $SID $RUN $OUT | tail -6" | tr -d '\r'
  mkdir -p "ev/$EVN"
  bash tools/vm.sh "sudo tar -cf - -C $OUT ." | tar -xf - -C "ev/$EVN"
  ( cd "ev/$EVN" && sha256sum -c --quiet SHA256SUMS ) && echo "  pulled ev/$EVN: $(grep -c . "ev/$EVN/SHA256SUMS") files, SHA256SUMS hold"
  cp logs/rc6/${EVN}_*.log "ev/$EVN/" 2>/dev/null || true
  real_status after; echo "  target status after: $(tail -1 "logs/rc6/${EVN}_target_status_after.log")"
  python -I - "logs/rc6/${EVN}_target_status_before.log" "logs/rc6/${EVN}_target_status_after.log" <<'PY'
import json, sys
def res(p):
    for line in open(p, encoding="utf-8"):
        if line.startswith("{") and '"RESULT"' in line:
            return json.loads(line)["result"]
a, b = res(sys.argv[1]), res(sys.argv[2])
print("  R7 on the run target unchanged by the copy:", a == b)
sys.exit(0 if a == b else 1)
PY
  if [ -z "${KEEP:-}" ]; then copy MODE=drop
  else echo "  copy $CN kept (KEEP=1): drop it with vm_copy_target6.sh MODE=drop COPY=$CN once its last use is done"; fi
  echo "== $(date -u +%FT%TZ) done"
} 2>&1 | tee "$L"
