#!/usr/bin/env bash
# PRIVATE (workstation): the analyses of the full run R7, once its last slice has ended and that slice's evidence
# (with the run's stored pages) is pulled, in order, stopping at the first failure. No provider request.
#   1. on the VM, as root, read only, with the installed release's Python and the target's data folder (where every
#      record's dom_key resolves, the carried ones' included), the run's export staged beside the tools:
#      the four named product pages (pdp_terms6.py), the named records traced (trace_record.py), the tiles of the
#      digital examples (tile_text.py), the two price-per-measure traces (ppm_embedded.py), the source excerpts of
#      every record (excerpts.py) and the Coupons route of every run of the target (coupons_route_check.py);
#   2. on the workstation, from the evidence: Cat Food 27021 (cat_food_record.py), the named offer products
#      (named_offers.py), the coverage against the 1.9 queue (coverage_vs_queue6.py), the listings above the
#      window and their subdivisions (branches6.py), the sample checks (check_sample.py, the named UPCs and 20 at
#      random with seed 1, as in the 1.10.0rc5 delivery), the no-refetch check over the whole run and the requests
#      in flight.
# Usage: after_run6.sh RUN_ID LAST_EVN R7_FOLDER...       (LAST_EVN: the last slice, collected without SKIP_STORED)
set -euo pipefail
cd [redacted:workstation-path]
RUN="$1"; LAST="$2"; shift 2
R7=("$@")
[[ "$RUN" =~ ^[0-9A-Z]{26}$ ]] || { echo "bad run id"; exit 2; }
EV="ev/$LAST"
PRE="${PRE:-pub6/pre/evidence}"   # a scratch folder for a test
LOG="${LOG:-logs/rc6/after_run_$LAST.log}"
[ ! -e "$LOG" ] || { echo "REFUSED: $LOG exists"; exit 2; }
[ -d "$EV/stored/$RUN/live/dom" ] || { echo "REFUSED: $EV holds no stored pages of $RUN"; exit 2; }
for f in products.json provenance.json coverage_reconciliation.csv coverage_by_csv_row.csv; do
  [ -f "$EV/export/$f" ] || { echo "REFUSED: $EV/export/$f is missing (the run has not exported)"; exit 2; }
done
mkdir -p "$PRE/accuracy" "$PRE/coverage" "$PRE/operations" "$PRE/samples/R7" "$PRE/ledger"
NAMED_PDP=(0001780014939 0001780014941 0002310014848 0003980014995)
PPM=(0084024314377 0001280052496)
OFFERS=(0081675102373 0086001079386 0001820020352 0073679800140)
T=[redacted:workstation-path]/after_run
rm -rf "$T"; mkdir -p "$T/stage/tools" "$T/stage/export"
{
  echo "== $(date -u +%FT%TZ) after R7 (run $RUN, last slice $LAST; slices ${R7[*]})"
  cp ops6/pdp_terms6.py ops/trace_record.py ops/tile_text.py ops/ppm_embedded.py ops/excerpts.py \
     ops/coupons_route_check.py "$T/stage/tools/"
  cp "$EV/export/products.json" "$EV/export/provenance.json" "$T/stage/export/"
  cp "$EV/db_page_fetches.csv" "$T/stage/"
  ( cd "$T/stage" && sha256sum tools/* export/* db_page_fetches.csv ) > "$T/stage/STAGED.sha256"
  echo "== the VM: named product pages, traces, tiles, PPM, excerpts, Coupons route"
  tar -cf - -C "$T" stage | VM_STDIN=1 bash tools/vm.sh "sudo env RUN=$RUN NP='${NAMED_PDP[*]}' PP='${PPM[*]}' NO='${OFFERS[*]}' bash -c '
    set -euo pipefail
    D=\$(mktemp -d); trap \"rm -rf \$D\" EXIT
    tar -xf - -C \$D; cd \$D/stage; sha256sum -c --quiet STAGED.sha256
    PY=/opt/marianos-collector/current/venv/bin/python
    DATA=\$(sed -n \"s#^MARIANOS_COLLECTOR_DATA_DIR=##p\" /etc/marianos-collector/collector.env)
    DB=\$(sed -n \"s#^MARIANOS_COLLECTOR_DATABASE_URL=postgresql://[^/]*/\\([^?]*\\).*#\\1#p\" /etc/marianos-collector/collector.env)
    LIVE=\$DATA/runs/marianos-53100502-pickup/\$RUN/live
    mkdir out
    \$PY -I tools/pdp_terms6.py out/PDP_TERMS_R7.json \$LIVE db_page_fetches.csv export \$NP > out/PDP_TERMS_R7.txt
    \$PY -I tools/trace_record.py export \$DATA \$PP \$NP \$NO > out/NAMED_UPCS_R7_trace_record.txt
    \$PY -I tools/tile_text.py export \$DATA out/DIGITAL_EXAMPLES_R7_TILES.txt \$NP > /dev/null
    \$PY -I tools/ppm_embedded.py \$LIVE export out/PPM_DISPLAYED_AND_EMBEDDED_R7.txt \$PP > /dev/null
    \$PY -I tools/excerpts.py export \$DATA out/source_excerpts.jsonl.gz > out/excerpts_summary.txt
    python3.12 -I tools/coupons_route_check.py out/COUPONS_ROUTE_READINGS.txt \$DB > /dev/null
    tar -cf - -C \$D/stage out
  '" > "$T/vm_out.tar"
  tar -xf "$T/vm_out.tar" -C "$T"
  ls -l "$T/out"
  cp "$T/out/PDP_TERMS_R7.json" "$T/out/PDP_TERMS_R7.txt" "$T/out/NAMED_UPCS_R7_trace_record.txt" \
     "$T/out/DIGITAL_EXAMPLES_R7_TILES.txt" "$T/out/PPM_DISPLAYED_AND_EMBEDDED_R7.txt" \
     "$T/out/COUPONS_ROUTE_READINGS.txt" "$PRE/accuracy/"
  cat "$T/out/PDP_TERMS_R7.txt"
  tail -3 "$T/out/excerpts_summary.txt"
  echo "== the samples folder (samples/R7: products.json beside its source excerpts); the sample checks"
  cp "$EV/export/products.json" "$T/out/source_excerpts.jsonl.gz" "$PRE/samples/R7/"
  cp ops/check_sample.py "$PRE/samples/check_sample.py"
  python -I ops/check_sample.py "$PRE/samples/R7" "${PPM[@]}" "${NAMED_PDP[@]}" "${OFFERS[@]}" \
    > "$PRE/accuracy/NAMED_UPCS_R7_check_sample.txt"
  tail -4 "$PRE/accuracy/NAMED_UPCS_R7_check_sample.txt"
  python -I ops/check_sample.py "$PRE/samples/R7" --random 20 --seed 1 > "$PRE/samples/CHECK_R7_RANDOM_20_seed1.txt"
  head -1 "$PRE/samples/CHECK_R7_RANDOM_20_seed1.txt"; tail -1 "$PRE/samples/CHECK_R7_RANDOM_20_seed1.txt"
  python -I ops/check_sample.py "$PRE/samples/R7" --random 20 --seed 1 --fresh-only \
    > "$PRE/samples/CHECK_R7_FRESH_RANDOM_20_seed1.txt"
  head -1 "$PRE/samples/CHECK_R7_FRESH_RANDOM_20_seed1.txt"; tail -1 "$PRE/samples/CHECK_R7_FRESH_RANDOM_20_seed1.txt"
  echo "== Cat Food 27021"
  python -I ops/cat_food_record.py "$PRE/accuracy/CAT_FOOD_27021_R7.txt" "$EV" | tail -6
  echo "== the named offer products"
  python -I ops/named_offers.py "$EV/export" "$PRE/accuracy/NAMED_OFFERS_R7.txt" | tail -6
  echo "== coverage against the 1.9 queue"
  python -I ops6/coverage_vs_queue6.py tmp/INCOMPLETE_QUEUE_190.csv "$EV/export/coverage_reconciliation.csv" R7 \
    "$PRE/coverage/QUEUE_190_VS_R7.csv" | tail -8
  cp "$EV/export/coverage_by_csv_row.csv" "$PRE/coverage/COVERAGE_BY_CSV_ROW_R7.csv"
  echo "== listings above the window and their subdivisions"
  python -I ops6/branches6.py "$EV" "$PRE/coverage/BRANCHES_R7.csv" "$PRE/coverage/BRANCH_PAGES_R7.csv" \
    > "$PRE/coverage/BRANCHES_R7_SUMMARY.json"
  cat "$PRE/coverage/BRANCHES_R7_SUMMARY.json"
  echo "== the operator tools' own records (pulled by after_slice6.sh from each stage's folder on the VM)"
  mkdir -p "$PRE/operations/slice_stops"
  for f in "${R7[@]}"; do
    for NAME in slice_stop slice_stop2 kill_recover; do
      if [ -f "logs/rc6/${NAME}_$f.log" ]; then cp "logs/rc6/${NAME}_$f.log" "$PRE/operations/slice_stops/"; echo "  $f: ${NAME}_$f.log copied"
      else echo "  $f: no $NAME record"; fi
    done
    # a unit resumed in the slice's stage (resume_in_stage6.sh, the walkthrough's resume) has its own record
    for x in logs/rc6/slice_stop_marianos-stage-*_"$f".log; do
      [ -f "$x" ] || continue
      cp "$x" "$PRE/operations/slice_stops/"; echo "  $f: $(basename "$x") copied"
    done
  done
  echo "== no re-fetch over the whole run; requests in flight over every live stage of 1.10.0rc6"
  python -I ops/no_refetch.py "$EV/db_listing_pages.csv" "$EV/db_collection_segments.csv" \
    "$EV/db_deferred_requests.csv" "$PRE/operations/NO_REFETCH_R7.txt" | tail -3
  FOLDERS=(ev/P7 ev/R6a ev/R6fin ev/P8)   # P8: the product-page pilot, a live stage of 1.10.0rc6 on its own target
  for f in "${R7[@]}"; do FOLDERS+=("ev/$f"); done
  python -I ops/peak_in_flight.py "$PRE/operations/PEAK_IN_FLIGHT.txt" "${FOLDERS[@]}" | tail -4
  cp "$PRE/operations/PEAK_IN_FLIGHT.txt" "$PRE/ledger/PEAK_IN_FLIGHT.txt"
  echo "== repeated pages and re-asks by hour, every live stage of 1.10.0rc6"
  python -I ops6/repeats_by_hour.py "$PRE/operations/REPEATED_PAGES_BY_HOUR_RC6.csv" "${FOLDERS[@]}" | tail -3
  python -I ops6/reask_outcomes.py "$PRE/operations/REASK_OUTCOMES_BY_HOUR_RC6.csv" "${FOLDERS[@]}" | tail -2
  echo "== $(date -u +%FT%TZ) done"
} 2>&1 | tr -d '\r' | tee "$LOG"
