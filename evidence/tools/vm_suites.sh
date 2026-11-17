#!/usr/bin/env bash
# On the owner VM (detached): the pinned candidate's own checks from its verified tree, one after the other, each
# recorded with its UTC times and exit code in $W/logs/SUITES.jsonl. Throwaway PostgreSQL through pgserver.
set -u
W="${W:?}"; L="$W/logs"; cd "$W/src" || exit 9
step() {
  local label="$1"; shift
  local s e code
  s=$(date -u +%FT%TZ)
  "$@" > "$L/$label.log" 2>&1; code=$?
  e=$(date -u +%FT%TZ)
  printf '{"label":"%s","utc_start":"%s","utc_end":"%s","exit_code":%s,"last_line":%s,"log_sha256":"%s"}\n' \
    "$label" "$s" "$e" "$code" "$(tail -1 "$L/$label.log" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()[:300]))')" \
    "$(sha256sum "$L/$label.log" | cut -c1-64)" >> "$L/SUITES.jsonl"
}
: > "$L/SUITES.jsonl"
step uv_sync uv sync --frozen
PY="$W/src/.venv/bin/python"
step chromium_deps sudo "$PY" -m playwright install-deps chromium
step chromium "$PY" -m playwright install chromium
step unit "$PY" -m pytest tests/unit -q -p no:cacheprovider -rfEs "--junitxml=$L/unit.junit.xml"
step ruff_check "$PY" -m ruff check .
step ruff_format "$PY" -m ruff format --check .
step mypy "$PY" -m mypy
step c1_cases "$PY" -m pytest tests/integration/test_reask_c1.py -q -p no:cacheprovider -rfEs "--junitxml=$L/c1_cases.junit.xml"
step publication_result "$PY" -m pytest tests/integration/test_publication_result.py -q -p no:cacheprovider -rfEs "--junitxml=$L/publication_result.junit.xml"
step integration "$PY" -m pytest tests/integration -q -p no:cacheprovider -rfEs "--junitxml=$L/integration.junit.xml"
echo "postgres processes of the test servers left: $(pgrep -u "$USER" -c postgres || true)" > "$L/after_suites.txt"
date -u +%FT%TZ >> "$L/after_suites.txt"
echo ALL_DONE >> "$L/SUITES.jsonl"
