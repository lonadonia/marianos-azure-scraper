#!/usr/bin/env bash
# Stage Q (TEST_PLAN_180 Amendments 3-5): the candidate checked out in the clean worktree C:/m6/qwt (3b2650a for Q1,
# b1d69d1 for Q1b, ec3b6fe from Q1c; each run records its own source revision), database
# marianos_q180 on the local pgserver, configuration copy C:/m6/q180/config, data C:/m6/q180/data.
# usage: q180.sh <marianos-collector arguments>
cd /c/m6/qwt/headless/marianos-azure-headless || exit 1
export PSYCOPG_IMPL=python
# libpq for psycopg's pure-Python implementation: the one pgserver ships (the workstation has no other)
export PATH="$PWD/.venv/Lib/site-packages/pgserver/pginstall/bin:$PATH"
PORT=$(sed -n 4p 'C:\m6\pg\data\postmaster.pid' | tr -d '\r')
export MARIANOS_COLLECTOR_DATABASE_URL="postgresql+psycopg://postgres:@127.0.0.1:${PORT}/marianos_q180"
export MARIANOS_COLLECTOR_CONFIG='C:\m6\q180\config\collector.yaml'
export MARIANOS_COLLECTOR_DATA_DIR='C:\m6\q180\data'
export MARIANOS_COLLECTOR_ACTOR="hamza-qualification"
# The key file: read by the collector itself (only its fingerprint is ever shown).
export OXYLABS_WEB_API_KEY_FILE='<projects>\marianos-scraper\data\local\oxylabs.env'
unset OXYLABS_WEB_API_KEY SCRAPFLY_API_KEY SCRAPFLY_API_KEY_FILE MARIANOS_COLLECTOR_SOURCE_COMMIT
exec .venv/Scripts/python.exe -X utf8 -m marianos_headless.cli "$@"
