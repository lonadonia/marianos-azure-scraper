#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root: sudo bash -s < this): the published state of the target every 1.10.0rc6 run used,
# read only (no provider request): pub_state.sh on the database and data folder that
# /etc/marianos-collector/collector.env names, for the store marianos-53100502-pickup.
set -euo pipefail
E=/etc/marianos-collector/collector.env
DB=$(sed -n 's#^MARIANOS_COLLECTOR_DATABASE_URL=postgresql://[^/]*/\([^?]*\).*#\1#p' "$E")
DATA=$(sed -n 's#^MARIANOS_COLLECTOR_DATA_DIR=##p' "$E")
[ -n "$DB" ] && [ -d "$DATA" ] || { echo "REFUSED: no database or data folder named in $E"; exit 2; }
exec /var/lib/marianos-collector/ops111/pub_state.sh "$DB" "$DATA" marianos-53100502-pickup
