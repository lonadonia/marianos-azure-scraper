#!/usr/bin/env bash
# The suites of collector 1.10.0rc7 at ec10cde, one step at a time, run in foreground chunks (a Claude Code
# background shell is stopped when memory is low): `suite.sh STEP...`, where STEP is git_status, uv_sync, unit,
# ruff_check, ruff_format, mypy, c1_cases, publication_result, integration_<name> (tests/integration/test_<name>.py),
# build, cli_version, wheel_metadata, git_status_after, or `all_done` (refuses unless every step has a record).
# Each step: its log, its JUnit file for pytest steps, and one JSON line in SUITES.jsonl (last_line written by
# Python; the driver of 0073277 lost it to a heredoc). The tests send nothing out: the proxy is a closed port.
set -u -o pipefail
OUT=[redacted:workstation-path]/rc7/suites_ec10cde
PKG=[redacted:workstation-path]/wt7/headless/marianos-azure-headless
HEAD_WANT=ec10cde09feedf5a5bab04169e6dbadb8592b5ce
cd "$PKG" || exit 9
[ "$(git rev-parse HEAD)" = "$HEAD_WANT" ] || { echo "not $HEAD_WANT"; exit 9; }
export PUBLICATION_EVIDENCE_DIR=[redacted:workstation-path]/rc7/ev_ec10cde HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 NO_PROXY=127.0.0.1,localhost
mkdir -p [redacted:workstation-path]/rc7/ev_ec10cde
touch "$OUT/SUITES.jsonl"
INTEG=$(for f in tests/integration/test_*.py; do n=$(basename "$f" .py); echo "integration_${n#test_}"; done)
ALL="git_status uv_sync unit ruff_check ruff_format mypy c1_cases publication_result $INTEG build cli_version wheel_metadata git_status_after"
recorded() { grep -q "\"label\": \"$1\"" "$OUT/SUITES.jsonl"; }
step() {
  local label=$1; shift
  local start end code sha
  start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  timeout 2400 "$@" > "$OUT/$label.log" 2>&1
  code=$?
  end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  sha=$(sha256sum "$OUT/$label.log" | cut -d' ' -f1)
  python -I -c 'import json,sys; t=[l.rstrip("\r") for l in open(sys.argv[2],encoding="utf-8",errors="replace").read().splitlines() if l.strip() and not l.startswith("{\"ts\"")]; print(json.dumps({"label":sys.argv[1],"head":sys.argv[7],"utc_start":sys.argv[3],"utc_end":sys.argv[4],"exit_code":int(sys.argv[5]),"last_line":(t[-1] if t else ""),"log_sha256":sys.argv[6]}))' \
    "$label" "$OUT/$label.log" "$start" "$end" "$code" "$sha" "$(git rev-parse HEAD)" >> "$OUT/SUITES.jsonl"
  tail -1 "$OUT/SUITES.jsonl" | python -I -c 'import json,sys; d=json.loads(sys.stdin.read()); print(d["label"].ljust(40), "exit", d["exit_code"], d["utc_start"][11:] + "-" + d["utc_end"][11:], d["last_line"][:90])'
}
pytest_step() { local label=$1; shift; step "$label" uv run --frozen pytest -q -p no:cacheprovider --junitxml="$OUT/$label.junit.xml" "$@"; }
echo "CHUNK $(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >> "$OUT/SUITES.jsonl"
for s in "$@"; do
  if [ "$s" = all_done ]; then
    for a in $ALL; do recorded "$a" || { echo "no record for $a"; exit 9; }; done
    echo ALL_DONE >> "$OUT/SUITES.jsonl"; echo ALL_DONE; continue
  fi
  recorded "$s" && { echo "$s already recorded"; continue; }
  case "$s" in
    git_status) step git_status bash -c 'git status --short; git rev-parse HEAD HEAD:headless/marianos-azure-headless; echo clean=$(test -z "$(git status --short)" && echo yes || echo no)';;
    uv_sync) step uv_sync uv sync --frozen;;
    unit) pytest_step unit tests/unit;;
    ruff_check) step ruff_check uv run --frozen ruff check src tests tools;;
    ruff_format) step ruff_format uv run --frozen ruff format --check src tests tools;;
    mypy) step mypy uv run --frozen mypy src tools/replay_routes.py;;
    c1_cases) pytest_step c1_cases tests/integration/test_reask_c1.py;;
    publication_result) pytest_step publication_result tests/integration/test_publication_result.py;;
    integration_*) f="tests/integration/test_${s#integration_}.py"; [ -f "$f" ] || { echo "no $f"; exit 9; }; pytest_step "$s" "$f";;
    build) rm -rf dist/rc7; step build uv build --wheel --offline --out-dir dist/rc7;;
    cli_version) step cli_version uv run --frozen marianos-collector --version;;
    wheel_metadata) step wheel_metadata python -I -c "import zipfile,glob,hashlib; w=sorted(glob.glob('dist/rc7/*.whl'))[-1]; z=zipfile.ZipFile(w); m=[n for n in z.namelist() if n.endswith('METADATA')][0]; print(w.replace(chr(92),'/').split('/')[-1]); [print(l) for l in z.read(m).decode().splitlines() if l.startswith(('Name:','Version:'))]; print('sha256', hashlib.sha256(open(w,'rb').read()).hexdigest())";;
    git_status_after) step git_status_after bash -c 'git status --short; echo clean=$(test -z "$(git status --short)" && echo yes || echo no)';;
    *) echo "unknown step $s"; exit 9;;
  esac
done
