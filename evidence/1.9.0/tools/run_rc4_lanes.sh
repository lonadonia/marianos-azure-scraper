#!/bin/bash
# The 1.9.0rc4 regression (two listing lanes never save a page whose answer has not arrived) on 1.9.0rc3
# (9090537, the commit before the fix: expected to FAIL, judged by its output) and on 1.9.0rc4 (8abc2c1: expected
# to pass). On 1.9.0rc3 the test file of 1.9.0rc4 is copied into a clean checkout under another name, only that
# test is run against the tests' own throwaway PostgreSQL, and the copy is removed. Nothing leaves the machine.
set -u
TEST=test_two_lanes_never_save_a_page_whose_answer_has_not_arrived
SRC=/c/m8/wt/headless/marianos-azure-headless/tests/integration/test_partitions_190.py
run() { # label checkout dest_name log copied(yes/no)
  local label=$1 tree=$2 dest=$3 log=$4 copied=$5
  cd "$tree/headless/marianos-azure-headless" || exit 1
  local rev; rev=$(git rev-parse HEAD)
  if [ "$copied" = yes ]; then cp "$SRC" "tests/integration/$dest"; fi
  { echo "label: $label"; echo "revision: $rev"; echo "utc_start: $(date -u +%FT%TZ)";
    if [ "$copied" = yes ]; then echo "test: tests/integration/$dest::$TEST (the file of 1.9.0rc4, copied)";
    else echo "test: tests/integration/$dest::$TEST (the revision's own file)"; fi; } > "$log"
  PATH="$PWD/.venv/Lib/site-packages/pgserver/pginstall/bin:$PATH" PSYCOPG_IMPL=python PYTHONUTF8=1 \
    .venv/Scripts/python.exe -m pytest "tests/integration/$dest::$TEST" -p no:cacheprovider -q -rfE --tb=short >> "$log" 2>&1
  echo "exit: $?" >> "$log"; echo "utc_end: $(date -u +%FT%TZ)" >> "$log"
  if [ "$copied" = yes ]; then rm -f "tests/integration/$dest"; fi
  echo "checkout clean after the run: $([ -z "$(git status --short)" ] && echo yes || echo no)" >> "$log"
}
run RC4_LANES_on_9090537 /c/m8/t19 test_partitions_190_rc4.py /c/m8/evidence/rc4_lanes_on_9090537.log yes
run RC4_LANES_on_8abc2c1 /c/m8/wt test_partitions_190.py /c/m8/evidence/rc4_lanes_on_8abc2c1.log no
echo done
