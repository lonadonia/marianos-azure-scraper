#!/usr/bin/env bash
# The focused tests of OR-25 and OR-26 (committed in 8eec040, unchanged since) on 1.10.0rc6 (d77f306 with those test
# files added), on 8eec040 (the code of 021b23f) and on 1.10.0rc7 (ec10cde); one JSON line per step; one side a call.
set -u -o pipefail
OUT=[redacted:workstation-path]/rc7/ba
export HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 NO_PROXY=127.0.0.1,localhost
UNIT="tests/unit/test_route_audit_rc7.py tests/unit/test_contract_csv_rc7.py"
INTEG="tests/integration/test_route_audit_rc7.py"
step() {
  local label=$1; shift
  local start end code sha
  start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  timeout 1500 "$@" > "$OUT/$label.log" 2>&1
  code=$?
  end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  sha=$(sha256sum "$OUT/$label.log" | cut -d' ' -f1)
  python -I -c 'import json,sys; t=[l.rstrip("\r") for l in open(sys.argv[2],encoding="utf-8",errors="replace").read().splitlines() if l.strip() and not l.startswith("{\"ts\"")]; print(json.dumps({"label":sys.argv[1],"utc_start":sys.argv[3],"utc_end":sys.argv[4],"exit_code":int(sys.argv[5]),"last_line":(t[-1] if t else ""),"log_sha256":sys.argv[6]}))' "$label" "$OUT/$label.log" "$start" "$end" "$code" "$sha" >> "$OUT/STEPS.jsonl"
}
side() {  # label dir
  local label=$1 dir=$2
  cd "$dir/headless/marianos-azure-headless" || exit 9
  export PUBLICATION_EVIDENCE_DIR=[redacted:workstation-path]/rc7/ba/ev_$label
  mkdir -p "$PUBLICATION_EVIDENCE_DIR"
  [ "${SKIP_IDENTITY:-}" ] || step "${label}_identity" bash -c 'echo "HEAD $(git rev-parse HEAD)"; echo "src tree at HEAD $(git rev-parse HEAD:headless/marianos-azure-headless/src)"; echo "src changed from HEAD: $(git status --short -- src | wc -l) file(s)"; echo "test files not in HEAD (copied from 8eec040):"; git status --short -- tests; echo "version $(grep -m1 ^version pyproject.toml)"'
  # each unit file on its own: on 1.10.0rc6 the route audit module does not exist, and that collection error
  # would stop pytest before the CSV contract tests
  [ "${SKIP_COMBINED:-}" ] || step "${label}_unit" uv run --frozen pytest -q -p no:cacheprovider -rA --junitxml="$OUT/${label}_unit.junit.xml" $UNIT
  step "${label}_unit_route_audit" uv run --frozen pytest -q -p no:cacheprovider -rA --junitxml="$OUT/${label}_unit_route_audit.junit.xml" tests/unit/test_route_audit_rc7.py
  step "${label}_unit_contract_csv" uv run --frozen pytest -q -p no:cacheprovider -rA --junitxml="$OUT/${label}_unit_contract_csv.junit.xml" tests/unit/test_contract_csv_rc7.py
  [ "${ONLY_UNIT_SPLIT:-}" ] && return 0
  step "${label}_integration" uv run --frozen pytest -q -p no:cacheprovider -rA --junitxml="$OUT/${label}_integration.junit.xml" $INTEG
}
case "${1:-}" in
  before_rc6)
    [ "$(git -C [redacted:workstation-path]/rc7/rc6check rev-parse HEAD)" = d77f3065c757b8b962524dbf8d9961dec212e72b ] || { echo "rc6check is not at d77f306"; exit 9; }
    side before_rc6_d77f306 [redacted:workstation-path]/rc7/rc6check;;
  before_dev)
    cd [redacted:workstation-path]/rc7/rc6check && rm -f headless/marianos-azure-headless/tests/integration/test_route_audit_rc7.py headless/marianos-azure-headless/tests/unit/test_route_audit_rc7.py headless/marianos-azure-headless/tests/unit/test_contract_csv_rc7.py && git checkout -q -f --detach 8eec040
    side before_dev_8eec040 [redacted:workstation-path]/rc7/rc6check;;
  after)
    [ "$(git -C [redacted:workstation-path]/wt7 rev-parse HEAD)" = ec10cde09feedf5a5bab04169e6dbadb8592b5ce ] || { echo "wt7 is not at ec10cde"; exit 9; }
    side after_rc7_ec10cde [redacted:workstation-path]/wt7
    echo ALL_DONE >> "$OUT/STEPS.jsonl";;
  *) echo "usage: driver.sh before_rc6|before_dev|after"; exit 9;;
esac
