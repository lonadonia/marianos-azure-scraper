#!/usr/bin/env bash
# On the owner VM (sudo bash -s < this): the final candidate 1.10.0rc4 installed by the documented scripts into a
# NEW isolated target (database marianos_rc4, data /var/lib/marianos-collector/rc4/data), so that its runs carry no
# record of the rc3 pilots. Before the switch: a backup of the pilots' target (marianos_q110) and a restore check of
# that backup into a scratch database (row counts of every table compared). The q110 target stays as it is.
set -euo pipefail
W=[redacted:vm-home]/m10r4d
VERSION=1.10.0rc4
COMMIT=570ff7cce9d45a913963d495593f0f9d89c3c41e
OLD_DB=marianos_q110
DB=marianos_rc4
ETC=/etc/marianos-collector
TS=$(date -u +%Y%m%dT%H%M%SZ)
say() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 2; }
[ -e /opt/marianos-collector/releases/$VERSION ] && { echo "REFUSED: release $VERSION is already installed"; exit 2; }
systemctl list-units --no-legend 'marianos-*' | grep -q running && { echo "REFUSED: a collector unit is running"; exit 9; }
( cd "$W/rel" && sha256sum -c --quiet "$W/rel.SHA256SUMS" ) && say "release files match their recorded hashes"

say "== backup of the pilots' target before the switch (backup.sh)"
DB_NAME=$OLD_DB bash "$W/rel/backup.sh" "before-rc4-switch-$OLD_DB"
DUMP=$(ls -1t /var/lib/marianos-collector/backups/*_before-rc4-switch-$OLD_DB.dump | head -1)
say "== restore check of $DUMP into a scratch database"
SCR=zz_restorecheck_${OLD_DB}_$TS
runuser -u postgres -- createdb -O marianos "$SCR"
runuser -u marianos -- pg_restore --no-owner --exit-on-error -d "$SCR" < "$DUMP"
counts() {
  runuser -u marianos -- psql -X -At -d "$1" -c "SELECT string_agg(t, ' ' ORDER BY t) FROM (SELECT tablename AS t FROM pg_tables WHERE schemaname='public') x" |
    tr ' ' '\n' | while read -r t; do [ -n "$t" ] && printf '%s %s\n' "$t" "$(runuser -u marianos -- psql -X -At -d "$1" -c "SELECT count(*) FROM \"$t\"")"; done
}
counts "$OLD_DB" > "$W/logs/restorecheck_original.txt"
counts "$SCR" > "$W/logs/restorecheck_restored.txt"
if cmp -s "$W/logs/restorecheck_original.txt" "$W/logs/restorecheck_restored.txt"; then
  say "RESTORE CHECK: identical row counts in $(wc -l < "$W/logs/restorecheck_original.txt") tables"
else
  say "RESTORE CHECK: DIFFERENT"; diff "$W/logs/restorecheck_original.txt" "$W/logs/restorecheck_restored.txt" || true; exit 5
fi
runuser -u postgres -- dropdb "$SCR" && say "scratch database dropped"

say "== prepare_host.sh (database $DB)"
DB_NAME=$DB bash "$W/rel/prepare_host.sh"
say "== prepare_host.sh (database marianos_pubtest: the isolated publication target)"
DB_NAME=marianos_pubtest bash "$W/rel/prepare_host.sh"
install -d -m 750 -o marianos -g marianos /var/lib/marianos-collector/pubtest /var/lib/marianos-collector/pubtest/data
say "== install_release.sh $VERSION $COMMIT"
bash "$W/rel/install_release.sh" "$VERSION" "$COMMIT" "$W/rel/marianos_azure_headless-$VERSION-py3-none-any.whl" "$W/rel/requirements.lock.txt" "$W/rel/config.tgz"

say "== the new isolated target's env file (the q110 one kept as a dated copy)"
cp -p "$ETC/collector.env" "$ETC/collector.env.before-rc4-$TS"
install -d -m 750 -o marianos -g marianos /var/lib/marianos-collector/rc4 /var/lib/marianos-collector/rc4/data
umask 027
cat > "$ETC/collector.env.new" <<EOF
# /etc/marianos-collector/collector.env: the isolated target of the final candidate (written $TS). No secret here.
MARIANOS_COLLECTOR_DATABASE_URL=postgresql://marianos@/$DB?host=/var/run/postgresql
MARIANOS_COLLECTOR_CONFIG=$ETC/config.$VERSION/collector.yaml
MARIANOS_COLLECTOR_CONFIG_DIR=$ETC/config.$VERSION
MARIANOS_COLLECTOR_DATA_DIR=/var/lib/marianos-collector/rc4/data
OXYLABS_WEB_API_KEY_FILE=$ETC/oxylabs.env
MARIANOS_COLLECTOR_LOG_LEVEL=INFO
EOF
chown root:marianos "$ETC/collector.env.new"; chmod 640 "$ETC/collector.env.new"
mv "$ETC/collector.env.new" "$ETC/collector.env"

say "== migrations, configuration, checks on the new target"
marianos db-upgrade
marianos sync-config
marianos validate-config --check-db
marianos status

say "== rollback check (code only): current -> previous -> current"
v() { /opt/marianos-collector/current/venv/bin/python -I -c 'import marianos_headless; print(marianos_headless.__version__)'; }
say "before: $(readlink /opt/marianos-collector/current) version $(v)"
bash "$W/rel/rollback.sh"
say "after rollback: $(readlink /opt/marianos-collector/current) version $(v)"
marianos validate-config --check-db
bash "$W/rel/rollback.sh"
say "after roll-forward: $(readlink /opt/marianos-collector/current) version $(v)"
marianos validate-config --check-db

say "== result"
readlink /opt/marianos-collector/current; cat /opt/marianos-collector/current/release.env
grep -i "^marianos" /opt/marianos-collector/current/installed.txt
sha256sum /opt/marianos-collector/current/SOURCES.sha256
( cd "$ETC/config.$VERSION" && sha256sum -- * )
runuser -u postgres -- psql -Atc "select 'databases: '||string_agg(datname, ', ' order by datname) from pg_database where not datistemplate"
say "done"
