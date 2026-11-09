#!/bin/bash
# Installs one release of marianos-collector from its wheel and the locked, hashed requirements. Run as root
# after prepare_host.sh, from the folder holding this script and the other deploy/vm files:
#
#   install_release.sh VERSION COMMIT WHEEL REQUIREMENTS CONFIG_TGZ
#
# WHEEL is the package built from the release commit COMMIT (the full revision), REQUIREMENTS the lockfile
# exported with hashes (`uv export --frozen --no-dev --no-emit-project`), CONFIG_TGZ the release's config/
# folder. The release goes to /opt/marianos-collector/releases/VERSION (refused if it exists: nothing is
# overwritten), with these scripts and release.env (the source commit every run records). The configuration
# goes to /etc/marianos-collector/config only when that folder does not exist, otherwise next to it as
# config.VERSION for review; collector.env likewise only when absent. `current` then points at the new
# release, `previous` at the one before (rollback.sh) and /usr/local/sbin/marianos at current's wrapper.
# The database is not touched: back it up (backup.sh), then run `marianos db-upgrade`.
set -euo pipefail

VERSION="$1"; COMMIT="$2"; WHEEL="$3"; REQS="$4"; CONFIG_TGZ="$5"
HERE="$(cd "$(dirname "$0")" && pwd)"
SVC_USER="${SVC_USER:-marianos}"
BASE=/opt/marianos-collector
DEST="$BASE/releases/$VERSION"
ETC=/etc/marianos-collector

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 2; }
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo "COMMIT must be the full revision" >&2; exit 2; }
[ -e "$DEST" ] && { echo "$DEST exists: refusing to overwrite a release" >&2; exit 2; }
for f in "$WHEEL" "$REQS" "$CONFIG_TGZ" "$HERE/marianos" "$HERE/collector.env.example"; do
  [ -f "$f" ] || { echo "missing $f" >&2; exit 2; }
done

install -d -m 755 "$DEST" "$DEST/deploy"
python3.12 -m venv "$DEST/venv"
"$DEST/venv/bin/pip" install --quiet --no-cache-dir --disable-pip-version-check --require-hashes \
  --only-binary=:all: -r "$REQS"
"$DEST/venv/bin/pip" install --quiet --no-cache-dir --disable-pip-version-check --no-deps "$WHEEL"
install -m 644 "$WHEEL" "$REQS" "$CONFIG_TGZ" "$HERE/collector.env.example" "$DEST/deploy/"
install -m 755 "$HERE/marianos" "$HERE"/*.sh "$DEST/deploy/"
printf 'MARIANOS_COLLECTOR_SOURCE_COMMIT=%s\n' "$COMMIT" > "$DEST/release.env"
(cd "$DEST/deploy" && sha256sum -- * > "$DEST/SOURCES.sha256")
"$DEST/venv/bin/pip" freeze --all > "$DEST/installed.txt"

cfg="$ETC/config"
if [ -e "$cfg" ]; then cfg="$ETC/config.$VERSION"; fi
install -d -m 750 -o root -g "$SVC_USER" "$cfg"
tar -xzf "$CONFIG_TGZ" -C "$cfg" --no-same-owner
chown -R root:"$SVC_USER" "$cfg"; chmod -R u=rwX,g=rX,o= "$cfg"
if [ ! -e "$ETC/collector.env" ]; then
  install -m 640 -o root -g "$SVC_USER" "$HERE/collector.env.example" "$ETC/collector.env"
fi

if [ -L "$BASE/current" ]; then ln -sfn "$(readlink "$BASE/current")" "$BASE/previous"; fi
ln -sfn "$DEST" "$BASE/current"
ln -sfn "$BASE/current/deploy/marianos" /usr/local/sbin/marianos
echo "installed $VERSION ($COMMIT) in $DEST; configuration in $cfg; current -> $(readlink "$BASE/current")"
