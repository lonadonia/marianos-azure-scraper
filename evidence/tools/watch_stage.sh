#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root). The operator's stops for a live stage that the collector does not enforce itself.
# Every count is taken from the watcher's start: a resumed run keeps its earlier slices' rows, and only this slice's
# rows are judged (on 2026-11-16 R6a ended with 12 re-asks answered and none recovered; counted over the whole run,
# that would stop every later slice at its first poll).
#   - more than 2 of the stage's ledger reservations left unknown;
#   - 10 re-asks answered in this slice and none recovered its request;
#   - 16 or more answers in this slice for a page 2 or later (new or repeated), of which PCT% or more repeat an
#     earlier page: the site serving page 1 again, which on 2026-11-16 rose with the hour from 10% at 03Z to 86% at
#     23Z (a slice in those hours spends about 3 submissions on each such page and reads almost none). PCT is read
#     at the watcher's start from $OPS/repeat_stop_pct (an integer from 5 to 100), 50 when absent: 50 protects the
#     credit; a lower value protects the run's re-asks (two per page), set by the operator before a slice.
# Any of them stops the stage's unit with SIGTERM (the collector records a resumable stop). One progress line per poll.
# Usage: watch_stage.sh UNIT STAGE_ID DB LOG
set -u
UNIT="$1"; STAGE="$2"; DB="$3"; LOG="$4"
LED=/var/lib/oxylabs-marianos-20261116/ledger.sqlite3
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
PCT=$(cat /var/lib/marianos-collector/ops-rc6/repeat_stop_pct 2>/dev/null | tr -dc '0-9')
[[ "$PCT" =~ ^[0-9]+$ ]] && [ "$PCT" -ge 5 ] && [ "$PCT" -le 100 ] || PCT=50
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
log "watch start unit=$UNIT stage=$STAGE db=$DB; rows judged from $START; repeat stop at ${PCT}%"
while :; do
  act=$(systemctl is-active "$UNIT" 2>/dev/null)
  run=$(q "SELECT id FROM runs ORDER BY started_at DESC NULLS LAST LIMIT 1" | tr -d ' ')
  if [ -n "$run" ]; then
    st=$(q "SELECT status||'|'||coalesce(stop_code,'-') FROM runs WHERE id='$run'")
    pages=$(q "SELECT count(*)||' pages, '||count(*) FILTER (WHERE state='completed')||' completed' FROM listing_pages WHERE run_id='$run'")
    upcs=$(q "SELECT count(DISTINCT upc) FROM product_observations WHERE run_id='$run'")
    dr=$(q "SELECT count(*), count(*) FILTER (WHERE state='waiting'), count(*) FILTER (WHERE state='recovered' AND resolved_at >= '$START'), count(*) FILTER (WHERE state='exhausted'), coalesce(sum((SELECT count(*) FROM jsonb_array_elements(d.attempts) a WHERE (a->>'ordinal')::int >= 1 AND (a->>'answered')::boolean AND (a->>'observed_at')::timestamptz >= '$START')),0) FROM deferred_requests d WHERE run_id='$run'")
    rp=$(q "SELECT count(*) FILTER (WHERE verdict='new'), count(*) FILTER (WHERE verdict='repeated') FROM listing_pages WHERE run_id='$run' AND requested_page >= 2 AND observed_at >= '$START'")
  else
    st="-"; pages="-"; upcs="-"; dr="0|0|0|0|0"; rp="0|0"
  fi
  led=$(ledger_states)
  unknown=$(printf '%s' "$led" | python3.12 -I -c 'import json,sys
try: print(json.load(sys.stdin).get("unknown",0))
except Exception: print(-1)')
  IFS='|' read -r d_all d_wait d_rec d_exh d_answered <<< "$(printf '%s' "$dr" | tr -d ' ')"
  IFS='|' read -r p_new p_rep <<< "$(printf '%s' "$rp" | tr -d ' ')"
  log "unit=$act run=$run status=$st pages=[$pages] distinct_upcs=$upcs deferred(all|wait|rec_slice|exh|answered_reasks_slice)=$dr page2plus_slice(new|repeated)=$rp ledger=$led"
  if [ "$act" = "active" ] && [ -z "$stopped" ]; then
    if [ "${unknown:-0}" -gt 2 ] 2>/dev/null; then
      stopped="more than 2 unknown outcomes ($unknown)"
    elif [ "${d_answered:-0}" -ge 10 ] 2>/dev/null && [ "${d_rec:-0}" -eq 0 ] 2>/dev/null; then
      stopped="10 re-asks answered in this slice ($d_answered) and none recovered"
    elif [ $(( ${p_new:-0} + ${p_rep:-0} )) -ge 16 ] 2>/dev/null && [ $(( 100 * ${p_rep:-0} )) -ge $(( PCT * (${p_new:-0} + ${p_rep:-0}) )) ] 2>/dev/null; then
      stopped="answers for a page 2 or later in this slice: ${p_new:-0} new, ${p_rep:-0} repeated (${PCT}% or more repeated)"
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
