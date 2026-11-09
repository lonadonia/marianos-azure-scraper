#!/bin/bash
# T06 on ac114d7 (the last commit before 1.9.0rc1's fix) and T07 on 1.8.0rc5 (ee5ec99): each test is copied into
# that checkout, run once against the tests' own throwaway PostgreSQL, and removed. Nothing leaves the machine.
set -u
run() { # label checkout test_source dest_name log
  local label=$1 tree=$2 src=$3 dest=$4 log=$5
  cd "$tree/headless/marianos-azure-headless" || exit 1
  local rev; rev=$(git rev-parse HEAD)
  cp "$src" "tests/integration/$dest"
  { echo "label: $label"; echo "revision: $rev"; echo "utc_start: $(date -u +%FT%TZ)";
    echo "test: tests/integration/$dest (copied from the 1.9.0 candidate's tests)"; } > "$log"
  PATH="$PWD/.venv/Lib/site-packages/pgserver/pginstall/bin:$PATH" PSYCOPG_IMPL=python PYTHONUTF8=1 \
    .venv/Scripts/python.exe -m pytest "tests/integration/$dest" -p no:cacheprovider -q -rfE --tb=short >> "$log" 2>&1
  echo "exit: $?" >> "$log"; echo "utc_end: $(date -u +%FT%TZ)" >> "$log"
  rm -f "tests/integration/$dest"
  echo "checkout clean after removal: $([ -z "$(git status --short)" ] && echo yes || echo no)" >> "$log"
}
run T06_on_ac114d7 /c/m8/t19 /c/m8/wt/headless/marianos-azure-headless/tests/integration/test_segment_end_t06.py \
  test_segment_end_t06.py /c/m8/evidence/t06_repro_ac114d7.log
run T07_on_ee5ec99 /c/m5/wt /c/m8/tools/repro/test_t07_on_rc5.py test_t07_on_rc5.py /c/m8/evidence/t07_repro_ee5ec99.log
echo done
