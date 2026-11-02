#!/usr/bin/env bash
# Run a Python script with the clean checkout's venv (C:/m6/qwt, 1.8.0rc4) and libpq on PATH: dbpy.sh script.py args
Q=/c/m6/qwt/headless/marianos-azure-headless
export PSYCOPG_IMPL=python
export PATH="$Q/.venv/Lib/site-packages/pgserver/pginstall/bin:$PATH"
exec "$Q/.venv/Scripts/python.exe" -X utf8 "$@"
