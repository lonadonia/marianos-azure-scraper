#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root). Collects one stage's evidence into OUT (no provider request):
# the collector's own status/export/validation, the database rows of the run (pages, deferred requests, events,
# provider usage, run), the stage's ledger rows and chain check, the journal, the watcher log, the harness records,
# and the run's stored data folder (captures). Ends with SHA256SUMS over every file.
# Usage: stage_evidence.sh STAGE_ID RUN_ID OUT
set -u
STAGE="$1"; RUN="$2"; OUT="$3"
OPS=/var/lib/marianos-collector/ops-rc6
ENVF=/etc/marianos-collector/collector.env
# the target the collector is configured for now, unless DB / DATA are given (the q110 target for S6 and S6b)
DB="${DB:-$(sed -n 's#^MARIANOS_COLLECTOR_DATABASE_URL=postgresql://[^/]*/\([^?]*\).*#\1#p' "$ENVF")}"
DATA="${DATA:-$(sed -n 's#^MARIANOS_COLLECTOR_DATA_DIR=##p' "$ENVF")}"
[ -n "$DB" ] && [ -n "$DATA" ] || { echo "no database or data folder"; exit 2; }
echo "target: database $DB, data $DATA"
# COPY_ENV (the env file of an isolated copy, vm_copy_target6.sh): the collector's own three commands below run on
# that copy as the service user, not through the harness on the target; DB and DATA must name the same copy.
if [ -n "${COPY_ENV:-}" ]; then
  cdb=$(sed -n 's#^MARIANOS_COLLECTOR_DATABASE_URL=postgresql://[^/]*/\([^?]*\).*#\1#p' "$COPY_ENV")
  cdata=$(sed -n 's#^MARIANOS_COLLECTOR_DATA_DIR=##p' "$COPY_ENV")
  [ "$cdb" = "$DB" ] && [ "$cdata" = "$DATA" ] || { echo "COPY_ENV names $cdb, $cdata: not DB and DATA"; exit 2; }
  grep -q '^OXYLABS_WEB_API_KEY_FILE=/dev/null$' "$COPY_ENV" || { echo "COPY_ENV holds a credential file"; exit 2; }
  col() { systemd-run --quiet --wait --pipe --collect --uid=marianos --gid=marianos -p EnvironmentFile="$COPY_ENV" \
    -p EnvironmentFile=/opt/marianos-collector/current/release.env -p WorkingDirectory=/var/lib/marianos-collector \
    -p NoNewPrivileges=yes -p PrivateTmp=yes -p MemoryMax=3G -p MemorySwapMax=0 \
    /opt/marianos-collector/current/venv/bin/marianos-collector "$@"; }
  echo "the collector's commands on the isolated copy (database $DB)"
else
  col() { mstage6 cli "$STAGE" -- "$@"; }
fi
LED=/var/lib/oxylabs-marianos-20261116/ledger.sqlite3
UNIT="${UNIT:-}"  # one unit name, or several separated by spaces
install -d -m 750 -o marianos -g marianos "$OUT" "$OUT/export"
q() { sudo -u marianos psql -X -q -d "$DB" -v ON_ERROR_STOP=1 -c "$1"; }
{
  echo "stage=$STAGE run=$RUN collected_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  col status --run "$RUN" > "$OUT/status_run.jsonl" 2>&1; echo "status exit $?"
  col export --run "$RUN" --out "$OUT/export" > "$OUT/export.jsonl" 2>&1; echo "export exit $?"
  col validate-export --run "$RUN" > "$OUT/validate_export.jsonl" 2>&1; echo "validate-export exit $?"
  q "\copy (SELECT * FROM runs WHERE id='$RUN') TO '$OUT/db_runs.csv' CSV HEADER"; echo "runs $?"
  q "\copy (SELECT * FROM listing_pages WHERE run_id='$RUN' ORDER BY observed_at, id) TO '$OUT/db_listing_pages.csv' CSV HEADER"; echo "listing_pages $?"
  q "\copy (SELECT * FROM deferred_requests WHERE run_id='$RUN' ORDER BY created_at) TO '$OUT/db_deferred_requests.csv' CSV HEADER"; echo "deferred $?"
  q "\copy (SELECT * FROM events WHERE run_id='$RUN' ORDER BY ts) TO '$OUT/db_events.csv' CSV HEADER" 2>&1 || q "\copy (SELECT * FROM events WHERE run_id='$RUN') TO '$OUT/db_events.csv' CSV HEADER"; echo "events $?"
  q "\copy (SELECT * FROM provider_usage WHERE run_id='$RUN' ORDER BY reserved_at, id) TO '$OUT/db_provider_usage.csv' CSV HEADER"; echo "provider_usage $?"
  q "\copy (SELECT * FROM node_coverage WHERE run_id='$RUN') TO '$OUT/db_node_coverage.csv' CSV HEADER" 2>&1; echo "node_coverage $?"
  q "\copy (SELECT * FROM page_fetches WHERE run_id='$RUN') TO '$OUT/db_page_fetches.csv' CSV HEADER" 2>&1; echo "page_fetches $?"
  q "\copy (SELECT * FROM tasks WHERE run_id='$RUN') TO '$OUT/db_tasks.csv' CSV HEADER" 2>&1; echo "tasks $?"
  q "\copy (SELECT * FROM audit_log ORDER BY ts) TO '$OUT/db_audit_log.csv' CSV HEADER" 2>&1; echo "audit_log $?"
  # each segment's bounds and end state (its code revision is in its SEGMENT_STARTED event), the store attestations,
  # the run's validation findings and exports, and the target's publications and pointer (all runs of the target)
  q "\copy (SELECT * FROM collection_segments WHERE run_id='$RUN' ORDER BY started_at) TO '$OUT/db_collection_segments.csv' CSV HEADER" 2>&1; echo "collection_segments $?"
  q "\copy (SELECT * FROM store_attestations WHERE run_id='$RUN' ORDER BY observed_at) TO '$OUT/db_store_attestations.csv' CSV HEADER" 2>&1; echo "store_attestations $?"
  q "\copy (SELECT * FROM validation_findings WHERE run_id='$RUN' ORDER BY created_at) TO '$OUT/db_validation_findings.csv' CSV HEADER" 2>&1; echo "validation_findings $?"
  q "\copy (SELECT * FROM exports WHERE run_id='$RUN' ORDER BY created_at) TO '$OUT/db_exports.csv' CSV HEADER" 2>&1; echo "exports $?"
  q "\copy (SELECT * FROM publications ORDER BY published_at) TO '$OUT/db_publications.csv' CSV HEADER" 2>&1; echo "publications $?"
  q "\copy (SELECT * FROM publication_pointer) TO '$OUT/db_publication_pointer.csv' CSV HEADER" 2>&1; echo "publication_pointer $?"
  sudo -u marianos python3.12 -I - "$LED" "$STAGE" "$OUT" <<'PY'
import csv, json, sqlite3, sys
led, stage, out = sys.argv[1:4]
con = sqlite3.connect(f"file:{led}?mode=ro", uri=True, timeout=15)
con.row_factory = sqlite3.Row
rows = [dict(r) for r in con.execute("SELECT * FROM reservations WHERE stage_id=? ORDER BY created_at", (stage,))]
with open(f"{out}/ledger_reservations.csv", "w", newline="", encoding="utf-8") as f:
    if rows:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
st = [dict(r) for r in con.execute("SELECT * FROM stages WHERE stage_id=?", (stage,))]
ev = [dict(r) for r in con.execute("SELECT * FROM events WHERE ref=? OR detail LIKE ? ORDER BY seq", (stage, f"%{stage}%"))]
json.dump({"stage": st, "events_naming_the_stage": ev}, open(f"{out}/ledger_stage.json", "w", encoding="utf-8"), indent=1)
by = {}
for r in rows:
    by[r["state"]] = by.get(r["state"], 0) + 1
print("ledger rows", len(rows), json.dumps(by, sort_keys=True))
PY
  sudo -u marianos python3.12 -I /var/lib/oxylabs-marianos-20261116/oxytrial_ledger.py --campaign oxylabs-marianos-20261116 verify-chain > "$OUT/ledger_chain.txt" 2>&1; echo "chain $?"
  for u in $UNIT; do journalctl -u "$u" --no-pager -o short-iso-precise > "$OUT/journal_$u.log" 2>&1; done
  for w in "$OPS/stages/$STAGE/"watch*.log; do [ -f "$w" ] && cp "$w" "$OUT/"; done
  python3.12 -I -c 'import json,sys; [print(l, end="") for l in open(sys.argv[1]) if json.loads(l).get("stage")==sys.argv[2]]' "$OPS/runs.jsonl" "$STAGE" > "$OUT/harness_runs.jsonl"
  python3.12 -I -c 'import json,sys; json.dump(json.load(open(sys.argv[1]))[sys.argv[2]], open(sys.argv[3],"w"), indent=1)' "$OPS/stages.json" "$STAGE" "$OUT/stage_record.json"
  if [ -n "${SKIP_STORED:-}" ]; then  # a slice of a run that goes on: its stored pages are copied with the last slice
    ( cd "$DATA/runs/marianos-53100502-pickup/$RUN" && find . -type f -printf "%P	%s
" | sort ) > "$OUT/stored_listing.tsv"
    echo "stored not copied (SKIP_STORED); listing of $(wc -l < "$OUT/stored_listing.tsv") files"
  else
    mkdir -p "$OUT/stored"
    cp -a "$DATA/runs/marianos-53100502-pickup/$RUN" "$OUT/stored/" && echo "stored copied"
  fi
} > "$OUT/COLLECT.log" 2>&1
chown -R marianos:marianos "$OUT"
( cd "$OUT" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )
cat "$OUT/COLLECT.log"; echo "files: $(find "$OUT" -type f | wc -l)  size: $(du -sh "$OUT" | cut -f1)"
