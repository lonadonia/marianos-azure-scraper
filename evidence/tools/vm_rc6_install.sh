#!/usr/bin/env bash
# PRIVATE OPS on the owner VM (sudo bash -s < this): the candidate 1.10.0rc6 installed by the documented scripts
# as the current release, ON THE SAME TARGET as 1.10.0rc5 (database marianos_rc5, data
# /var/lib/marianos-collector/rc5/data), where run F2 stopped and the store is held: the brief has the hold released
# for the new run only once this candidate is installed and its identity verified. Before the switch: a backup of
# marianos_rc5 (backup.sh) and a restore check of that backup into a scratch database (row counts of every table
# compared). The env file keeps its database and data folder and names the rc6 configuration; the earlier one is
# kept as a dated copy. Migrations, configuration, checks, and a rollback check (code only). No provider request.
set -euo pipefail
W=[redacted:vm-home]/m10r6c
VERSION=1.10.0rc6
COMMIT=d77f3065c757b8b962524dbf8d9961dec212e72b
DB=marianos_rc5
ETC=/etc/marianos-collector
TS=$(date -u +%Y%m%dT%H%M%SZ)
say() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 2; }
[ -e /opt/marianos-collector/releases/$VERSION ] && { echo "REFUSED: release $VERSION is already installed"; exit 2; }
systemctl list-units --no-legend 'marianos-*' | grep -q running && { echo "REFUSED: a collector unit is running"; exit 9; }
( cd "$W/rel" && sha256sum -c --quiet "$W/rel.SHA256SUMS" ) || { echo "REFUSED: the release files differ from their recorded hashes"; exit 3; }
say "release files match their recorded hashes"
grep -q "^MARIANOS_COLLECTOR_DATABASE_URL=postgresql://marianos@/$DB?" "$ETC/collector.env" || { echo "REFUSED: collector.env does not name $DB"; exit 4; }
say "before: $(readlink /opt/marianos-collector/current); $(grep -c . "$ETC/collector.env") lines in collector.env (database $DB)"

say "== backup of the target before the switch (backup.sh)"
DB_NAME=$DB bash "$W/rel/backup.sh" "before-rc6-switch-$DB"
DUMP=$(ls -1t /var/lib/marianos-collector/backups/*_before-rc6-switch-$DB.dump | head -1)
say "dump: $DUMP ($(stat -c %s "$DUMP") bytes, sha256 $(sha256sum "$DUMP" | cut -c1-64))"
say "== restore check of the dump into a scratch database"
SCR=zz_restorecheck_${DB}_$TS
runuser -u postgres -- createdb -O marianos "$SCR"
runuser -u marianos -- pg_restore --no-owner --exit-on-error -d "$SCR" < "$DUMP"
counts() {
  runuser -u marianos -- psql -X -At -d "$1" -c "SELECT string_agg(t, ' ' ORDER BY t) FROM (SELECT tablename AS t FROM pg_tables WHERE schemaname='public') x" |
    tr ' ' '\n' | while read -r t; do [ -n "$t" ] && printf '%s %s\n' "$t" "$(runuser -u marianos -- psql -X -At -d "$1" -c "SELECT count(*) FROM \"$t\"")"; done
}
counts "$DB" > "$W/logs/restorecheck_original.txt"
counts "$SCR" > "$W/logs/restorecheck_restored.txt"
if cmp -s "$W/logs/restorecheck_original.txt" "$W/logs/restorecheck_restored.txt"; then
  say "RESTORE CHECK: identical row counts in $(wc -l < "$W/logs/restorecheck_original.txt") tables"
else
  say "RESTORE CHECK: DIFFERENT"; diff "$W/logs/restorecheck_original.txt" "$W/logs/restorecheck_restored.txt" || true; exit 5
fi
runuser -u postgres -- dropdb "$SCR" && say "scratch database dropped"

say "== install_release.sh $VERSION $COMMIT"
bash "$W/rel/install_release.sh" "$VERSION" "$COMMIT" "$W/rel/marianos_azure_headless-$VERSION-py3-none-any.whl" "$W/rel/requirements.lock.txt" "$W/rel/config.tgz"

say "== the env file: same database and data folder, the rc6 configuration (the earlier file kept as a dated copy)"
cp -p "$ETC/collector.env" "$ETC/collector.env.before-rc6-$TS"
sed -e "s#^MARIANOS_COLLECTOR_CONFIG=.*#MARIANOS_COLLECTOR_CONFIG=$ETC/config.$VERSION/collector.yaml#" \
    -e "s#^MARIANOS_COLLECTOR_CONFIG_DIR=.*#MARIANOS_COLLECTOR_CONFIG_DIR=$ETC/config.$VERSION#" \
    -e "s#^\# /etc/marianos-collector/collector.env:.*#\# /etc/marianos-collector/collector.env: the target of 1.10.0rc5, now with 1.10.0rc6 (rewritten $TS). No secret here.#" \
    "$ETC/collector.env.before-rc6-$TS" > "$ETC/collector.env.new"
chown root:marianos "$ETC/collector.env.new"; chmod 640 "$ETC/collector.env.new"
mv "$ETC/collector.env.new" "$ETC/collector.env"
diff "$ETC/collector.env.before-rc6-$TS" "$ETC/collector.env" | sed 's#postgresql://[^ ]*#<database url>#' || true

say "== migrations, configuration, checks"
marianos db-upgrade
marianos sync-config
marianos validate-config --check-db
marianos status --store marianos-53100502-pickup

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
say "done"
