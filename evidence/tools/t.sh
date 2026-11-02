#!/usr/bin/env bash
# Local test bench: t.sh <pytest args>. PostgreSQL from pgserver, started by C:/m5/tools/pg.py at C:\m6\pg\data.
cd /c/m5/wt/headless/marianos-azure-headless || exit 1
export PSYCOPG_IMPL=python
export PATH="$PWD/.venv/Lib/site-packages/pgserver/pginstall/bin:$PATH"
PORT=$(sed -n 4p 'C:\m6\pg\data\postmaster.pid' | tr -d '\r')
export MARIANOS_COLLECTOR_TEST_DATABASE_URL="postgresql+psycopg://postgres:@127.0.0.1:${PORT}/marianos_test"
.venv/Scripts/python.exe -X utf8 - <<'EOF'
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
u = make_url(os.environ["MARIANOS_COLLECTOR_TEST_DATABASE_URL"])
e = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
with e.connect() as c:
    if not c.execute(text("SELECT 1 FROM pg_database WHERE datname='marianos_test'")).first():
        c.execute(text("CREATE DATABASE marianos_test"))
e.dispose()
EOF
exec .venv/Scripts/python.exe -X utf8 -m pytest -q --no-header -p no:cacheprovider "$@"
