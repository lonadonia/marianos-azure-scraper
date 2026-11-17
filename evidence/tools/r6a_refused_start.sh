#!/usr/bin/env bash
# PRIVATE (workstation): the operator check of slice R6a. While R6a's unit runs and holds the store (pages
# collected), a second start for the same store through the harness's refused-start (a gate refusing every
# submission, no ledger lease): it must exit 9 (busy) before any request. The expected failure passes only when its
# output shows the refusal (exit 9 and the busy event), never on the exit code alone.
set -uo pipefail
cd [redacted:workstation-path]
SID=M-R6a-full-run-110rc6-20261116
OUT=logs/rc6/R6a_refused_start.log
until bash tools/vm.sh 'n=$(sudo journalctl -u marianos-stage-r6a -o cat --no-pager | grep -c "\"event\": \"PAGE_COLLECTED\""); echo "pages collected: $n"; [ "$n" -ge 3 ]' 2>/dev/null; do
  bash tools/vm.sh 'systemctl is-active --quiet marianos-stage-r6a' || { echo "R6a is not active: no check" | tee "$OUT"; exit 3; }
  sleep 15
done
{
  echo "== $(date -u +%FT%TZ) R6a holds the store; a second start for the same store:"
  bash tools/vm.sh "systemctl is-active marianos-stage-r6a; sudo mstage6 refused-start $SID -- run --store marianos-53100502-pickup; echo \"second start exit \$?\""
  echo "== $(date -u +%FT%TZ) ledger rows with the purpose of a refused start (none expected):"
  bash tools/vm.sh "sudo -u marianos python3.12 -I -c 'import sqlite3,sys; con=sqlite3.connect(\"file:/var/lib/oxylabs-marianos-20261116/ledger.sqlite3?mode=ro\", uri=True); print(con.execute(\"SELECT count(*) FROM leases\").fetchone()[0], \"leases in all;\", con.execute(\"SELECT count(*) FROM leases WHERE released_at IS NULL\").fetchone()[0], \"open\")'"
} 2>&1 | tee "$OUT"
code=$(grep -o "second start exit [0-9]*" "$OUT" | grep -o "[0-9]*$")
if [ "$code" = "9" ] && grep -q '"exit_code": 9' "$OUT"; then echo "CHECK PASSED: the second start was refused (exit 9) with its refusal in the output"; else echo "CHECK FAILED: exit ${code:-none}"; fi | tee -a "$OUT"
