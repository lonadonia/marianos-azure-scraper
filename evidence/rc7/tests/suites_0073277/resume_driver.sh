#!/usr/bin/env bash
# Resumes the suites of 0073277 after the stop of 2026-11-21 ~20:53Z (Claude Code stopped the first driver for low
# memory during integration_publication_safety). Runs only the steps that had not finished, one at a time, appending
# to SUITES.jsonl after a line that records the interruption. The partial log of the interrupted step is kept as
# integration_publication_safety.interrupted.log. last_line is written by Python (the first driver's sed lost it).
set -u -o pipefail
OUT=[redacted:workstation-path]/rc7/suites_0073277
PKG=[redacted:workstation-path]/wt7/headless/marianos-azure-headless
cd "$PKG" || exit 9
[ "$(git rev-parse HEAD)" = 0073277c23bb15ccdbe269e1588a794c42f83f08 ] || { echo "not 0073277"; exit 9; }
[ -z "$(git status --short)" ] || { echo "worktree not clean"; exit 9; }
export PUBLICATION_EVIDENCE_DIR=[redacted:workstation-path]/rc7/ev_rc7_final HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 NO_PROXY=127.0.0.1,localhost
if [ -f "$OUT/integration_publication_safety.log" ] && [ ! -f "$OUT/integration_publication_safety.interrupted.log" ]; then
  mv "$OUT/integration_publication_safety.log" "$OUT/integration_publication_safety.interrupted.log"
fi
grep -q '^INTERRUPTED' "$OUT/SUITES.jsonl" || echo "INTERRUPTED 2026-11-21 about 20:53Z: Claude Code stopped the shell of the first driver for low memory during integration_publication_safety; its processes, still running, were stopped at 20:54Z (4 tests of that file had passed, no result written); the steps below were run by resume_driver.sh, from integration_publication_safety on" >> "$OUT/SUITES.jsonl"
echo "RESUMED $(date -u +%Y-%m-%dT%H:%M:%SZ) ${*}" >> "$OUT/SUITES.jsonl"
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
}
# run in the foreground in chunks: `resume_driver.sh NAME...` runs those integration files (NAME as in test_NAME.py);
# `resume_driver.sh finish` checks that every integration file has a record, then runs the last four steps
if [ "${1:-}" != finish ]; then
  for n in "$@"; do
    f="tests/integration/test_$n.py"
    [ -f "$f" ] || { echo "no $f"; exit 9; }
    grep -q "\"label\": \"integration_$n\"\|\"label\":\"integration_$n\"" "$OUT/SUITES.jsonl" && { echo "integration_$n already recorded"; continue; }
    step "integration_$n" uv run --frozen pytest -q -p no:cacheprovider --junitxml="$OUT/integration_$n.junit.xml" "$f"
    tail -1 "$OUT/SUITES.jsonl" | cut -c1-200
  done
  exit 0
fi
for f in tests/integration/test_*.py; do
  n=$(basename "$f" .py); n=${n#test_}
  grep -q "\"label\": \"integration_$n\"\|\"label\":\"integration_$n\"" "$OUT/SUITES.jsonl" || { echo "integration_$n has no record"; exit 9; }
done
step build uv build --wheel --out-dir dist/rc7
step cli_version uv run --frozen marianos-collector --version
step wheel_metadata python -I -c "import zipfile,glob,hashlib; w=sorted(glob.glob('dist/rc7/*.whl'))[-1]; z=zipfile.ZipFile(w); m=[n for n in z.namelist() if n.endswith('METADATA')][0]; print(w.replace(chr(92),'/').split('/')[-1]); [print(l) for l in z.read(m).decode().splitlines() if l.startswith(('Name:','Version:'))]; print(hashlib.sha256(open(w,'rb').read()).hexdigest())"
step git_status_after bash -c 'git status --short; echo clean=$(test -z "$(git status --short)" && echo yes || echo no)'
echo ALL_DONE >> "$OUT/SUITES.jsonl"
