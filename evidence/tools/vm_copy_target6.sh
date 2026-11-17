#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root: sudo env MODE=... COPY=... bash -s < this): an isolated copy of the run target, with
# no provider credential, for an offline step on a run that must stay untouched on the real target. No provider
# request; the real target is only read (pg_dump; the data folder copied).
#   MODE=make COPY=<name> [SRC_DB=... SRC_DATA=...]   (the source: the configured target, or an earlier one)
#                           database marianos_<name> restored from a fresh pg_dump of the source's database, the data
#                           folder copied to ops-rc6/<name>/data, and ops-rc6/<name>/collector.env: the target's env
#                           with the copy's database and data folder and OXYLABS_WEB_API_KEY_FILE=/dev/null
#   MODE=cmd COPY=<name> ARGS="..." [REASON="..."]   one collector command on the copy (the service user, the copy's env, the
#                           current release; MemoryMax=3G, no swap); prints its output, then "exit N"
#   MODE=drop COPY=<name>   the copy's database dropped and its folder removed
set -euo pipefail
[[ "${COPY:-}" =~ ^[a-z0-9]{3,16}$ ]] || { echo "bad COPY"; exit 2; }
E=/etc/marianos-collector/collector.env
CURRENT=/opt/marianos-collector/current
OPS=/var/lib/marianos-collector/ops-rc6
D="$OPS/$COPY"
DBC="marianos_$COPY"
# the source is the configured target unless SRC_DB and SRC_DATA both name another (an earlier isolated target)
SRC_DB="${SRC_DB:-$(sed -n 's#^MARIANOS_COLLECTOR_DATABASE_URL=postgresql://[^/]*/\([^?]*\).*#\1#p' "$E")}"
SRC_DATA="${SRC_DATA:-$(sed -n 's#^MARIANOS_COLLECTOR_DATA_DIR=##p' "$E")}"
[ -n "$SRC_DB" ] && [ -d "$SRC_DATA" ] || { echo "REFUSED: no target in $E"; exit 2; }
[ "$DBC" != "$SRC_DB" ] || { echo "REFUSED: the copy would be the target"; exit 2; }
case "${MODE:-}" in
  make)
    [ ! -e "$D" ] || { echo "REFUSED: $D exists"; exit 2; }
    exists=$(sudo -u postgres psql -Atc "select count(*) from pg_database where datname='$DBC'")
    [ "$exists" = 0 ] || { echo "REFUSED: database $DBC exists"; exit 2; }
    install -d -m 0750 -o marianos -g marianos "$D"
    echo "$(date -u +%FT%TZ) dump of $SRC_DB"
    runuser -u marianos -- pg_dump -Fc -d "$SRC_DB" -f "$D/target.dump"
    sudo -u postgres createdb -O marianos "$DBC"
    runuser -u marianos -- pg_restore --no-owner --exit-on-error -d "$DBC" "$D/target.dump"
    echo "$(date -u +%FT%TZ) data folder copied"
    cp -a "$SRC_DATA" "$D/data"
    sed -e "s#^\(MARIANOS_COLLECTOR_DATABASE_URL=postgresql://[^/]*/\)[^?]*#\1$DBC#" \
        -e "s#^MARIANOS_COLLECTOR_DATA_DIR=.*#MARIANOS_COLLECTOR_DATA_DIR=$D/data#" \
        -e "s#^OXYLABS_WEB_API_KEY_FILE=.*#OXYLABS_WEB_API_KEY_FILE=/dev/null#" "$E" > "$D/collector.env"
    chown root:marianos "$D/collector.env"; chmod 0640 "$D/collector.env"
    grep -q "/$DBC" "$D/collector.env" && grep -q "^MARIANOS_COLLECTOR_DATA_DIR=$D/data$" "$D/collector.env" \
      && grep -q "^OXYLABS_WEB_API_KEY_FILE=/dev/null$" "$D/collector.env" || { echo "REFUSED: the copy's env is wrong"; exit 3; }
    for t in runs records listing_pages; do
      a=$(runuser -u marianos -- psql -Atc "select count(*) from $t" -d "$SRC_DB")
      b=$(runuser -u marianos -- psql -Atc "select count(*) from $t" -d "$DBC")
      echo "  $t: target $a, copy $b"; [ "$a" = "$b" ] || { echo "REFUSED: $t differs"; exit 3; }
    done
    echo "  data files: target $(find "$SRC_DATA" -type f | wc -l), copy $(find "$D/data" -type f | wc -l)"
    echo "$(date -u +%FT%TZ) copy $COPY made" ;;
  cmd)
    [ -s "$D/collector.env" ] || { echo "REFUSED: no copy $COPY"; exit 2; }
    read -r -a A <<< "${ARGS:?ARGS}"
    [ -z "${REASON:-}" ] || A+=(--reason "$REASON")   # one argument with spaces (stop --reason)
    set +e
    systemd-run --quiet --wait --pipe --collect --uid=marianos --gid=marianos \
      -p EnvironmentFile="$D/collector.env" -p EnvironmentFile="$CURRENT/release.env" \
      -p WorkingDirectory=/var/lib/marianos-collector -p NoNewPrivileges=yes -p PrivateTmp=yes \
      -p MemoryMax=3G -p MemorySwapMax=0 "$CURRENT/venv/bin/marianos-collector" "${A[@]}"
    echo "exit $?" ;;
  drop)
    sudo -u postgres dropdb --if-exists "$DBC"
    rm -rf "$D"
    echo "copy $COPY dropped" ;;
  *) echo "MODE is make, cmd or drop"; exit 2 ;;
esac
