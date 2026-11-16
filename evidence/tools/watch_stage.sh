#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root). The operator's stops for a live stage that the collector does not enforce itself:
#   - more than 2 of the stage's ledger reservations left unknown;
#   - 10 re-asks answered and none recovered its request.
# Either stops the stage's unit with SIGTERM (the collector records a resumable stop). One progress line per poll.
# Usage: watch_stage.sh UNIT STAGE_ID DB LOG
set -u
UNIT="$1"; STAGE="$2"; DB="$3"; LOG="$4"
LED=/var/lib/oxylabs-trial-20261103/ledger.sqlite3
q() { sudo -u marianos psql -X -q -At -F'|' -d "$DB" -c "$1" 2>&1 | tr '\n' ' '; }
ledger_states() {
  sudo -u marianos python3.12 -I -c '
import json, sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True, timeout=15)
print(json.dumps(dict(con.execute("SELECT state, count(*) FROM reservations WHERE stage_id=? GROUP BY state", (sys.argv[2],)).fetchall()), sort_keys=True))
' "$LED" "$STAGE" 2>&1
}
log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG"; }
stopped=""
log "watch start unit=$UNIT stage=$STAGE db=$DB"
while :; do
  act=$(systemctl is-active "$UNIT" 2>/dev/null)
  run=$(q "SELECT id FROM runs ORDER BY started_at DESC NULLS LAST LIMIT 1" | tr -d ' ')
  if [ -n "$run" ]; then
    st=$(q "SELECT status||'|'||coalesce(stop_code,'-') FROM runs WHERE id='$run'")
    pages=$(q "SELECT count(*)||' pages, '||count(*) FILTER (WHERE state='completed')||' completed' FROM listing_pages WHERE run_id='$run'")
    upcs=$(q "SELECT count(DISTINCT upc) FROM product_observations WHERE run_id='$run'")
    dr=$(q "SELECT count(*), count(*) FILTER (WHERE state='waiting'), count(*) FILTER (WHERE state='recovered'), count(*) FILTER (WHERE state='exhausted'), coalesce(sum((SELECT count(*) FROM jsonb_array_elements(d.attempts) a WHERE (a->>'ordinal')::int >= 1 AND (a->>'answered')::boolean)),0) FROM deferred_requests d WHERE run_id='$run'")
  else
    st="-"; pages="-"; upcs="-"; dr="0|0|0|0|0"
  fi
  led=$(ledger_states)
  unknown=$(printf '%s' "$led" | python3.12 -I -c 'import json,sys
try: print(json.load(sys.stdin).get("unknown",0))
except Exception: print(-1)')
  IFS='|' read -r d_all d_wait d_rec d_exh d_answered <<< "$(printf '%s' "$dr" | tr -d ' ')"
  log "unit=$act run=$run status=$st pages=[$pages] distinct_upcs=$upcs deferred(all|wait|rec|exh|answered_reasks)=$dr ledger=$led"
  if [ "$act" = "active" ] && [ -z "$stopped" ]; then
    if [ "${unknown:-0}" -gt 2 ] 2>/dev/null; then
      stopped="more than 2 unknown outcomes ($unknown)"
    elif [ "${d_answered:-0}" -ge 10 ] 2>/dev/null && [ "${d_rec:-0}" -eq 0 ] 2>/dev/null; then
      stopped="10 re-asks answered ($d_answered) and none recovered"
    fi
    if [ -n "$stopped" ]; then
      log "OPERATOR STOP: $stopped -> systemctl stop $UNIT"
      systemctl stop "$UNIT"
      log "unit after stop: $(systemctl is-active "$UNIT" 2>/dev/null)"
    fi
  fi
  case "$act" in active|activating|deactivating) ;; *) log "unit not active ($act): watch ends"; break;; esac
  sleep 30
done
