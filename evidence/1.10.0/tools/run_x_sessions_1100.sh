#!/bin/bash
# The candidate's offline checks again, one after the other, in the clean extraction of its tree (C:/m8/x1100/source,
# git archive with core.autocrlf=false, installed with uv sync --frozen --offline), recorded by runlog.py. The C1 and
# publication cases write no observation files here (C1_EVIDENCE_DIR and PUBLICATION_EVIDENCE_DIR unset), so the
# candidate's own case files cannot be touched. Ends with the extraction checked again against the tree.
set -u
X=C:/m8/x1100/source
L=C:/m8/logs/tests1100
PY=C:/w6/py312/pkg/tools/python.exe
VPY=$X/.venv/Scripts/python.exe
TREEISH=a1040f79919b8e876e0b69cd909cecf9363780b4:headless/marianos-azure-headless
export PSYCOPG_IMPL=python PYTHONUTF8=1
export PATH="/c/m8/x1100/source/.venv/Lib/site-packages/pgserver/pginstall/bin:$PATH"
unset C1_EVIDENCE_DIR PUBLICATION_EVIDENCE_DIR
cd /c/m8/x1100/source || exit 9
"$PY" -I C:/m8/tools/tree_check_1100.py "$X" C:/m8/wt "$TREEISH" "$L/x_tree_check_start.json" || { echo "TREE CHANGED BEFORE THE SESSIONS"; exit 8; }
"$PY" -I C:/m8/tools/runlog.py x_unit "$X" "$L" -- "$VPY" -m pytest tests/unit -q -p no:cacheprovider -rfEs
"$PY" -I C:/m8/tools/runlog.py x_ruff_check "$X" "$L" -- "$VPY" -m ruff check .
"$PY" -I C:/m8/tools/runlog.py x_ruff_format "$X" "$L" -- "$VPY" -m ruff format --check .
"$PY" -I C:/m8/tools/runlog.py x_mypy "$X" "$L" -- "$VPY" -m mypy
"$PY" -I C:/m8/tools/runlog.py x_c1_cases "$X" "$L" -- "$VPY" -m pytest tests/integration/test_reask_c1.py -p no:cacheprovider -q -rfEs "--junitxml=$L/x_c1_cases.junit.xml"
"$PY" -I C:/m8/tools/runlog.py x_publication_result "$X" "$L" -- "$VPY" -m pytest tests/integration/test_publication_result.py -p no:cacheprovider -q -rfEs "--junitxml=$L/x_publication_result.junit.xml"
"$PY" -I C:/m8/tools/tree_check_1100.py "$X" C:/m8/wt "$TREEISH" "$L/x_tree_check_after_sessions.json"
echo "tree check after the sessions: exit $?"
date -u +%FT%TZ
echo "ALL DONE"
