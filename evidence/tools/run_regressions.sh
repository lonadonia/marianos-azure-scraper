#!/usr/bin/env bash
# The five regressions of the brief against the defective source (4815ed4, release 1.7.0rc2) and the working tree.
set -u
WT=/c/m5/wt/headless/marianos-azure-headless
OLD=/c/m6/old184/headless/marianos-azure-headless
OUT=/c/m6/ev/regress
PY=$WT/.venv/Scripts/python.exe
export PSYCOPG_IMPL=python
export PATH="$WT/.venv/Lib/site-packages/pgserver/pginstall/bin:$PATH"
PORT=$(sed -n 4p 'C:\m6\pg\data\postmaster.pid' | tr -d '\r')
rm -rf /c/m6/old184; mkdir -p /c/m6/old184 "$OUT"
git -C /c/m5/wt archive 4815ed4 headless/marianos-azure-headless | tar -x -C /c/m6/old184 || exit 1
cp "$WT/tests/listing_site.py" "$WT/tests/synthetic_marianos.py" "$OLD/tests/"
cp "$WT/tests/integration/test_page_regressions.py" "$OLD/tests/integration/"
"$PY" -X utf8 - "$PORT" <<'EOF'
import sys
from sqlalchemy import create_engine, text
e = create_engine(f"postgresql+psycopg://postgres:@127.0.0.1:{sys.argv[1]}/postgres", isolation_level="AUTOCOMMIT")
with e.connect() as c:
    for d in ("marianos_old_test",):
        if not c.execute(text("SELECT 1 FROM pg_database WHERE datname=:d"), {"d": d}).first():
            c.execute(text(f"CREATE DATABASE {d}"))
e.dispose()
EOF
cd "$OLD" || exit 1
MARIANOS_COLLECTOR_TEST_DATABASE_URL="postgresql+psycopg://postgres:@127.0.0.1:${PORT}/marianos_old_test" \
PYTHONPATH="C:/m6/old184/headless/marianos-azure-headless/src" PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -X utf8 -c "import marianos_headless; print(marianos_headless.__file__, marianos_headless.__version__)" > "$OUT/old_4815ed4.log" 2>&1
MARIANOS_COLLECTOR_TEST_DATABASE_URL="postgresql+psycopg://postgres:@127.0.0.1:${PORT}/marianos_old_test" \
PYTHONPATH="C:/m6/old184/headless/marianos-azure-headless/src" PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -X utf8 -m pytest -q --no-header -p no:cacheprovider --tb=line \
  tests/integration/test_page_regressions.py >> "$OUT/old_4815ed4.log" 2>&1
echo "old exit=$?"
cd "$WT" || exit 1
MARIANOS_COLLECTOR_TEST_DATABASE_URL="postgresql+psycopg://postgres:@127.0.0.1:${PORT}/marianos_test" \
  "$PY" -X utf8 -c "import marianos_headless; print(marianos_headless.__file__, marianos_headless.__version__)" > "$OUT/new_worktree.log" 2>&1
MARIANOS_COLLECTOR_TEST_DATABASE_URL="postgresql+psycopg://postgres:@127.0.0.1:${PORT}/marianos_test" \
  "$PY" -X utf8 -m pytest -q --no-header -p no:cacheprovider --tb=line \
  tests/integration/test_page_regressions.py >> "$OUT/new_worktree.log" 2>&1
echo "new exit=$?"
grep -vE '^\{"ts"' "$OUT/old_4815ed4.log" | tail -14 | cut -c1-170
grep -vE '^\{"ts"' "$OUT/new_worktree.log" | tail -4 | cut -c1-170
