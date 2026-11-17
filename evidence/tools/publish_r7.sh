#!/usr/bin/env bash
# PRIVATE (workstation): the publication of the full run R7 on the target every 1.10.0rc6 run used, then two
# refusals showing that an incomplete run cannot replace the published dataset; no provider request. Each step's
# output goes to logs/rc6/pub6/ (a command's log ends with its exit code); the published state is read before and
# after each step (pub_state_target6.sh, read only) and compared (ops/pub_compare.py).
#   publish_r7.sh R7_RUN P7_RUN R6_RUN
#   1. state before; 2. publish R7 (the collector publishes it only if its gates pass, else refuses with exit 6);
#   3. state after: different from 1 in every section if R7 was published, equal to 1 if it was refused;
#   then, only if R7 was published:
#   4. publish P7 (a pilot): refused; 5. state after: equal to 3 in every section;
#   6. publish R6 (rejected, incomplete): refused; 7. state after: equal to 3 in every section.
# An expected refusal passes only when its output shows it (COMMAND_REFUSED with exit_code 6) and the exit is 6.
set -euo pipefail
cd [redacted:workstation-path]
R7="$1"; P7="$2"; R6="$3"
for r in "$R7" "$P7" "$R6"; do [[ "$r" =~ ^[0-9A-Z]{26}$ ]] || { echo "bad run id $r"; exit 2; }; done
L=logs/rc6/pub6
[ ! -e "$L" ] || { echo "REFUSED: $L exists"; exit 2; }
mkdir -p "$L"
state() {  # LABEL
  VM_STDIN=1 bash tools/vm.sh "sudo bash -s" < ops6/pub_state_target6.sh | tr -d '\r' > "$L/pub_state_$1.txt"
  echo "  $L/pub_state_$1.txt: $(wc -l < "$L/pub_state_$1.txt") lines"
}
publish() {  # RUN NAME
  { echo "$(date -u +%FT%TZ) publish --run $1"; bash tools/vm.sh "sudo marianos publish --run $1; echo \"exit \$?\""; } \
    2>&1 | tr -d '\r' > "$L/$2.log" || true
  echo "  $L/$2.log: $(tail -1 "$L/$2.log")"
}
refused() {  # NAME
  grep -q '"event": "COMMAND_REFUSED"' "$L/$1.log" && grep -q '"exit_code": 6' "$L/$1.log" \
    && [ "$(tail -1 "$L/$1.log")" = "exit 6" ]
}
compare() {  # A B NAME ARGS...
  local a="$1" b="$2" n="$3"; shift 3
  if python -I ops/pub_compare.py "$L/pub_state_$a.txt" "$L/pub_state_$b.txt" "$@" | tr -d '\r' > "$L/COMPARE_$n.txt"; then
    echo "  COMPARE_$n: $(tail -1 "$L/COMPARE_$n.txt")"; return 0
  fi
  echo "  COMPARE_$n: $(tail -1 "$L/COMPARE_$n.txt")"; return 1
}
ALL=(pointer publications "every file under published/" latest.json "exports of the published run")
{
  echo "== $(date -u +%FT%TZ) publication of R7 ($R7) on the run target; refusals of P7 ($P7) and R6 ($R6)"
  state 0_before_R7_publish
  publish "$R7" R7_publish
  state 1_after_R7_publish
  if [ "$(tail -1 "$L/R7_publish.log")" = "exit 0" ]; then
    compare 0_before_R7_publish 1_after_R7_publish before_vs_after_R7_publish --expect-different pointer publications \
      "every file under published/"
    publish "$P7" P7_publish_refused
    if refused P7_publish_refused; then echo "  CHECK PASSED: P7 refused (exit 6), the refusal in its output"
    else echo "  CHECK FAILED: P7 was not refused as expected"; exit 1; fi
    state 2_after_P7_refusal
    compare 1_after_R7_publish 2_after_P7_refusal R7_published_vs_after_P7_refusal --expect-equal "${ALL[@]}"
    publish "$R6" R6_publish_refused
    if refused R6_publish_refused; then echo "  CHECK PASSED: R6 refused (exit 6), the refusal in its output"
    else echo "  CHECK FAILED: R6 was not refused as expected"; exit 1; fi
    state 3_after_R6_refusal
    compare 1_after_R7_publish 3_after_R6_refusal R7_published_vs_after_R6_refusal --expect-equal "${ALL[@]}"
  else
    echo "  R7 was NOT published ($(tail -1 "$L/R7_publish.log")): no published dataset exists on the target, so the"
    echo "  refusal checks against a published dataset are not run"
    compare 0_before_R7_publish 1_after_R7_publish before_vs_after_R7_refusal --expect-equal "${ALL[@]}"
  fi
  echo "== $(date -u +%FT%TZ) done"
} 2>&1 | tee "$L/PUBLISH_R7.log"
