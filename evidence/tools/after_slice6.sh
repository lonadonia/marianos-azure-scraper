#!/usr/bin/env bash
# PRIVATE (workstation): everything after one slice of R7 has ended, in order, each step's output kept in
# logs/rc6/after_<EVN>.log. No provider request.
#   1. stage_end6.sh: the stage's evidence collected on the VM, the stage closed with OUTCOME, the folder pulled and
#      checked, analyze_stage.py (SKIP_STORED=1 leaves the stored pages on the VM, for every slice but the last);
#   2. run_report.py over every R7 slice so far (the last folder holds every row of the run);
#   3. no_refetch.py and peak_in_flight.py on the run so far;
#   4. reproject6.py: the full run reprojected from R7's own rate, against the ledger's room after this slice;
#   5. repeats_by_hour.py and reask_outcomes.py over every live stage of 1.10.0rc6.
# Usage: [SKIP_STORED=1] after_slice6.sh KEY UNIT[,UNIT2] RUN_ID EVN 'OUTCOME' PREVIOUS_R7_FOLDERS...
set -euo pipefail
cd [redacted:workstation-path]
KEY="$1"; UNIT="$2"; RUN="$3"; EVN="$4"; OUTCOME="$5"; shift 5
PREV=("$@")
LOG="logs/rc6/after_$EVN.log"
# FROM=2: step 1 (stage_end6) already done and its folder pulled and checked (ev/EVN with SHA256SUMS): the steps from
# 2 on, appended to the same log (for a step after 1 that failed and was fixed).
FROM="${FROM:-1}"
if [ "$FROM" = 1 ]; then
  [ ! -e "$LOG" ] || { echo "REFUSED: $LOG exists"; exit 2; }
else
  [ "$FROM" = 2 ] && [ -e "$LOG" ] && [ -s "ev/$EVN/SHA256SUMS" ] || { echo "REFUSED: FROM=2 needs $LOG and ev/$EVN/SHA256SUMS"; exit 2; }
fi
{
  if [ "$FROM" = 1 ]; then
    echo "== $(date -u +%FT%TZ) after $EVN ($KEY, $UNIT, run $RUN)"
    bash ops6/stage_end6.sh "$KEY" "$UNIT" "$RUN" "$EVN" "$OUTCOME"
  else
    echo "== $(date -u +%FT%TZ) after $EVN: from step 2 (step 1, stage_end6, done above)"
  fi
  # the operator tools' own records, which stay in the stage's folder on the VM (stage_evidence6 collects only the
  # watchers' logs): the slice stopper beside the first unit (slice_stop.log), the one beside a unit started after
  # a planned kill (slice_stop2.log), and the kill-and-recovery record (kill_recover.log), each as logs/rc6/<name>_EVN.log
  SID=$(python -I -c "import json,sys; print(json.load(open(sys.argv[1], encoding='utf-8'))['stage_id'])" "ev/$EVN/stage_record.json" | tr -d '\r')
  [[ "$SID" =~ ^M-[A-Za-z0-9-]+$ ]] || { echo "bad stage id in ev/$EVN/stage_record.json"; exit 2; }
  # a unit resumed in the stage by resume_in_stage6.sh has its own slice stopper log (slice_stop_<unit>.log)
  EXTRA=$(bash tools/vm.sh "sudo sh -c 'cd /var/lib/marianos-collector/ops-rc6/stages/$SID && ls slice_stop_marianos-stage-*.log 2>/dev/null' | sed 's/[.]log$//'" | tr -d '\r' || true)
  for NAME in slice_stop slice_stop2 kill_recover $EXTRA; do
    [[ "$NAME" =~ ^[a-z0-9_-]+$ ]] || { echo "bad log name $NAME"; exit 2; }
    if bash tools/vm.sh "sudo test -f /var/lib/marianos-collector/ops-rc6/stages/$SID/$NAME.log"; then
      bash tools/vm.sh "sudo cat /var/lib/marianos-collector/ops-rc6/stages/$SID/$NAME.log" | tr -d '\r' > "logs/rc6/${NAME}_$EVN.log"
      echo "== $NAME: logs/rc6/${NAME}_$EVN.log ($(wc -l < "logs/rc6/${NAME}_$EVN.log") lines): $(tail -1 "logs/rc6/${NAME}_$EVN.log" | cut -c1-160)"
    else
      echo "== $NAME: none for $SID"
    fi
  done
  FOLDERS=()
  for f in "${PREV[@]}" "$EVN"; do FOLDERS+=("ev/$f"); done
  echo "== run report over: ${FOLDERS[*]}"
  python -I ops/run_report.py "${FOLDERS[@]}" | tail -1
  echo "== no re-fetch"
  python -I ops/no_refetch.py "ev/$EVN/db_listing_pages.csv" "ev/$EVN/db_collection_segments.csv" \
    "ev/$EVN/db_deferred_requests.csv" "logs/rc6/NO_REFETCH_$EVN.txt" | tail -3
  echo "== in flight"
  python -I ops/peak_in_flight.py "logs/rc6/PEAK_IN_FLIGHT_$EVN.txt" "${FOLDERS[@]}" | tail -4
  echo "== reprojection"
  python -I ops6/reproject6.py logs/rc6/ESTIMATE_1.10.0rc6.json "logs/rc6/ledger_after_$EVN.json" "${FOLDERS[@]}" \
    > "logs/rc6/REPROJECTION_after_$EVN.json"
  python -I -c "
import json, sys
d = json.load(open(sys.argv[1], encoding='utf-8'))
lo, hi = d['projection']['low'], d['projection']['high']
print('rate', d['submissions_per_counted_page'], 'subs/counted page;', d['pages_counted'], 'pages counted;',
      'room', d['envelope_room_submissions'], 'subs; pages left', lo['pages_left'], '-', hi['pages_left'],
      '; subs left', lo['submissions_left'], '-', hi['submissions_left'], '; short USD', lo['shortfall_usd'], '-',
      hi['shortfall_usd'], '; hours left', lo['hours_left_at_run_rate'], '-', hi['hours_left_at_run_rate'])
" "logs/rc6/REPROJECTION_after_$EVN.json"
  echo "== repeats and re-asks by hour (every live stage of 1.10.0rc6)"
  ALL=(ev/P7 ev/R6a ev/R6fin "${FOLDERS[@]}")
  python -I ops6/repeats_by_hour.py "logs/rc6/REPEATED_PAGES_BY_HOUR_after_$EVN.csv" "${ALL[@]}" | tail -2
  python -I ops6/reask_outcomes.py "logs/rc6/REASK_OUTCOMES_BY_HOUR_after_$EVN.csv" "${ALL[@]}" | tail -2
  echo "== $(date -u +%FT%TZ) done"
} 2>&1 | tr -d '\r' | tee -a "$LOG"
