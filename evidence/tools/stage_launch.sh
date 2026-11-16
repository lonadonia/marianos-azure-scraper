# PRIVATE OPS (owner VM, root; fed through `sudo bash -s` with STAGE_KEY, UNIT, SUBS, USD, RUNARGS exported first).
# Prepares one stage from stage_defs.json, sets the collector's own ceiling, opens the stage in the shared ledger,
# starts the run as a transient unit and the operator's watcher beside it. Stops at the first failing step.
set -euo pipefail
OPS=/var/lib/marianos-collector/ops111
DB="${DB:-$(sed -n 's#^MARIANOS_COLLECTOR_DATABASE_URL=postgresql://[^/]*/\([^?]*\).*#\1#p' /etc/marianos-collector/collector.env)}"
[ -n "$DB" ] || { echo "no database in collector.env"; exit 2; }
: "${STAGE_KEY:?}" "${UNIT:?}" "${SUBS:?}" "${USD:?}" "${RUNARGS:?}" "${REASON:?}"
echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) ledger before"
mstage ledger-status | python3.12 -I -c 'import json,sys; d=json.load(sys.stdin); m=d["projects"]["marianos"]; print(json.dumps({"chain": d["chain"], "active_lease": d["active_lease"], "marianos_spendable": m.get("spendable_in_envelope_usd"), "committed": d["committed_usd"]}))'
echo "== prepare $STAGE_KEY"
python3.12 -I "$OPS/prep_stage.py" "$OPS/stage_defs.json" "$STAGE_KEY" | tee "$OPS/prep_$STAGE_KEY.out"
ID=$(python3.12 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["stages"][sys.argv[2]]["stage_id"])' "$OPS/stage_defs.json" "$STAGE_KEY")
if [ -n "${PRE_CLI:-}" ]; then  # commands without provider requests before the stage, e.g. "db-upgrade;sync-config"
  IFS=";" read -ra pre <<< "$PRE_CLI"
  for c in "${pre[@]}"; do echo "== pre: $c"; mstage cli "$ID" -- $c; done
fi
echo "== status"
mstage cli "$ID" -- status || echo "(status exit $?)"
echo "== set-ceiling"
mstage cli "$ID" -- set-ceiling --provider oxylabs --submissions "$SUBS" --usd "$USD" --reason "$REASON"
mstage cli "$ID" -- provider-balance || echo "(provider-balance exit $?)"
echo "== open-stage"
mstage open-stage "$ID"
if [ -n "${NO_START:-}" ]; then  # the stage is opened and its ceiling set; its executions start later (walkthrough)
  echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) opened, not started (NO_START)"; exit 0
fi
echo "== start $UNIT"
# shellcheck disable=SC2086
mstage --unit "$UNIT" run "$ID" -- $RUNARGS
sleep 3
systemctl is-active "$UNIT" || true
systemd-run --quiet --unit="${UNIT/marianos-stage-/marianos-watch-}" "$OPS/watch_stage.sh" "$UNIT" "$ID" "$DB" "$OPS/stages/$ID/watch.log"
echo "watcher: $(systemctl is-active "${UNIT/marianos-stage-/marianos-watch-}")"
echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) started"
