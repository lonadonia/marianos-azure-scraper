#!/usr/bin/env bash
# Test bench on a chosen checkout and database: t2.sh <project dir> <database> <pytest args>
# PostgreSQL from pgserver (C:\m6\pg\data). Never two sessions on one database.
DIR="$1"; DB="$2"; shift 2
cd "$DIR" || exit 1
export PSYCOPG_IMPL=python
export PATH="$PWD/.venv/Lib/site-packages/pgserver/pginstall/bin:$PATH"
PORT=$(sed -n 4p 'C:\m6\pg\data\postmaster.pid' | tr -d '\r')
export MARIANOS_COLLECTOR_TEST_DATABASE_URL="postgresql+psycopg://postgres:@127.0.0.1:${PORT}/${DB}"
.venv/Scripts/python.exe -X utf8 - "$DB" <<'EOF'
import os, sys
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
u = make_url(os.environ["MARIANOS_COLLECTOR_TEST_DATABASE_URL"])
e = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
with e.connect() as c:
    if not c.execute(text("SELECT 1 FROM pg_database WHERE datname=:d"), {"d": sys.argv[1]}).first():
        c.execute(text(f'CREATE DATABASE "{sys.argv[1]}"'))
e.dispose()
EOF
exec .venv/Scripts/python.exe -X utf8 -m pytest -q --no-header -p no:cacheprovider "$@"
