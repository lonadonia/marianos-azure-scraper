#!/usr/bin/env bash
# PRIVATE (workstation): ends run R6 (01M7KBQ3XXMP3W3FK2EXE525EA) after its first slice, offline. R6a met the site
# serving page 1 again for 25 of 29 answers to a page 2 or later (23:40Z to 23:50Z on 2026-11-16) and every one of
# its 12 re-asks; resumed in a quieter hour, its 14 repeated pages would each have one re-ask left (the collector's
# limit is two), so a fresh run is started instead and R6 is finalized with what it collected:
#   1. the ledger's rows counted before; 2. stop (no execution is collecting it); 3. finalize (no provider request:
#   checks, gates and exports); 4. publish, which must refuse while the run is not a complete dataset (exit 6, the
#   refusal shown in the output); 5. the ledger's rows counted after (unchanged); 6. the store's status.
set -uo pipefail
cd [redacted:workstation-path]
RUN=01M7KBQ3XXMP3W3FK2EXE525EA
LOG=logs/rc6/R6_finalize.log
rows() { bash tools/vm.sh "sudo -u marianos python3.12 -I -c \"import sqlite3; con=sqlite3.connect('file:/var/lib/oxylabs-marianos-20261116/ledger.sqlite3?mode=ro', uri=True); print('ledger rows (campaign):', con.execute('SELECT count(*) FROM reservations').fetchone()[0], '| by state:', dict(con.execute('SELECT state, count(*) FROM reservations GROUP BY state').fetchall()))\""; }
{
  echo "== $(date -u +%FT%TZ) R6 finalize, offline"
  echo "-- 1. before"; rows
  echo "-- 2. stop"; bash tools/vm.sh "sudo marianos stop --run $RUN --reason 'R6 ended after its first slice: the site served page 1 again for most answers to a page 2 or later (23:40Z to 23:50Z); a fresh run R7 is started in a quieter hour'; echo \"exit \$?\""
  echo "-- 3. finalize"; bash tools/vm.sh "sudo marianos finalize --run $RUN; echo \"exit \$?\""
  echo "-- 4. publish (must refuse)"; bash tools/vm.sh "sudo marianos publish --run $RUN; echo \"exit \$?\""
  echo "-- 5. after"; rows
  echo "-- 6. status of the run"; bash tools/vm.sh "sudo marianos status --run $RUN; echo \"exit \$?\""
  echo "== $(date -u +%FT%TZ) end"
} > "$LOG" 2>&1
cat "$LOG" | cut -c1-600
