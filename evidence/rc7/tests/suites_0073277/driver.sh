#!/usr/bin/env bash
# Runs every suite on the committed tree, one step at a time; one JSON line per step in SUITES.jsonl.
set -u -o pipefail
OUT=[redacted:workstation-path]/rc7/suites_0073277
PKG=[redacted:workstation-path]/wt7/headless/marianos-azure-headless
cd "$PKG" || exit 9
export PUBLICATION_EVIDENCE_DIR=[redacted:workstation-path]/rc7/ev_rc7_final HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 NO_PROXY=127.0.0.1,localhost
mkdir -p [redacted:workstation-path]/rc7/ev_rc7_final
step() {
  local label=$1; shift
  local start end code last sha
  start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  timeout 2400 "$@" > "$OUT/$label.log" 2>&1
  code=$?
  end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  last=$(grep -v '^{"ts"' "$OUT/$label.log" | grep -v '^\s*$' | tail -1 | tr -d '\r' | sed 's/\/\\/g; s/"/\\"/g')
  sha=$(sha256sum "$OUT/$label.log" | cut -d' ' -f1)
  printf '{"label":"%s","head":"%s","utc_start":"%s","utc_end":"%s","exit_code":%d,"last_line":"%s","log_sha256":"%s"}\n' \
    "$label" "$(git rev-parse HEAD)" "$start" "$end" "$code" "$last" "$sha" >> "$OUT/SUITES.jsonl"
}
step git_status bash -c 'git status --short; git rev-parse HEAD HEAD:headless/marianos-azure-headless; echo clean=$(test -z "$(git status --short)" && echo yes || echo no)'
step uv_sync uv sync --frozen
step unit uv run --frozen pytest -q -p no:cacheprovider --junitxml="$OUT/unit.junit.xml" tests/unit
step ruff_check uv run --frozen ruff check src tests tools
step ruff_format uv run --frozen ruff format --check src tests tools
step mypy uv run --frozen mypy src tools/replay_routes.py
step c1_cases uv run --frozen pytest -q -p no:cacheprovider --junitxml="$OUT/c1_cases.junit.xml" tests/integration/test_reask_c1.py
step publication_result uv run --frozen pytest -q -p no:cacheprovider --junitxml="$OUT/publication_result.junit.xml" tests/integration/test_publication_result.py
for f in tests/integration/test_*.py; do
  n=$(basename "$f" .py)
  step "integration_${n#test_}" uv run --frozen pytest -q -p no:cacheprovider --junitxml="$OUT/integration_${n#test_}.junit.xml" "$f"
done
step build uv build --wheel --out-dir dist/rc7
step cli_version uv run --frozen marianos-collector --version
step wheel_metadata bash -c 'python -I -c "import zipfile,sys,glob; w=sorted(glob.glob(\"dist/rc7/*.whl\"))[-1]; z=zipfile.ZipFile(w); m=[n for n in z.namelist() if n.endswith(\"METADATA\")][0]; print(w.split(\"/\")[-1]); print(\"\n\".join(l for l in z.read(m).decode().splitlines() if l.startswith((\"Name:\",\"Version:\"))))"; sha256sum dist/rc7/*.whl | sed "s#dist/rc7/##"'
step git_status_after bash -c 'git status --short; echo clean=$(test -z "$(git status --short)" && echo yes || echo no)'
echo ALL_DONE >> "$OUT/SUITES.jsonl"
