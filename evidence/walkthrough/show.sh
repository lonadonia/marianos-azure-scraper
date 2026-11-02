#!/usr/bin/env bash
# Read-only views of the qualification database and exports (show180.py), in the clean worktree's environment.
cd /c/m6/qwt/headless/marianos-azure-headless || exit 1
export PSYCOPG_IMPL=python
export PATH="$PWD/.venv/Lib/site-packages/pgserver/pginstall/bin:$PATH"
exec .venv/Scripts/python.exe -I -X utf8 /c/m6/walk/show180.py "$@"
