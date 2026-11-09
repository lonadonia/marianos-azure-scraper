#!/bin/bash
# Points `current` back at the previous release (the code only). Run as root, with no collector command
# running. A database migrated by the newer release is not changed here: restore the backup taken before
# the upgrade (backup.sh) if the older release cannot read it (`marianos validate-config --check-db` tells).
set -euo pipefail

BASE=/opt/marianos-collector
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 2; }
[ -L "$BASE/previous" ] || { echo "no previous release recorded" >&2; exit 2; }
if systemctl list-units --no-legend 'marianos-*' | grep -q running; then
  echo "a collector unit is running: stop it first" >&2; exit 9
fi
now="$(readlink "$BASE/current")"; prev="$(readlink "$BASE/previous")"
ln -sfn "$prev" "$BASE/current"; ln -sfn "$now" "$BASE/previous"
echo "current -> $prev (was $now)"
