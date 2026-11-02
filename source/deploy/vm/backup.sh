#!/bin/bash
# A backup of the collector's database (pg_dump custom format) and configuration (no secrets), before an
# upgrade or a campaign. Run as root:  backup.sh LABEL
# Restore (only on a decision to roll back): pg_restore --clean --if-exists -d marianos_collector FILE.dump
# as the service user, after stopping every collector command.
set -euo pipefail

LABEL="${1:?label}"
SVC_USER="${SVC_USER:-marianos}"
DB_NAME="${DB_NAME:-marianos_collector}"
DIR=/var/lib/marianos-collector/backups
STAMP="$(date -u +%Y%m%dT%H%M%SZ)_${LABEL//[^A-Za-z0-9_.-]/_}"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 2; }
runuser -u "$SVC_USER" -- pg_dump -Fc -d "$DB_NAME" -f "$DIR/$STAMP.dump"
tar -czf "$DIR/$STAMP.config.tgz" -C /etc/marianos-collector --exclude='*.env' config
chown "$SVC_USER:$SVC_USER" "$DIR/$STAMP.config.tgz"; chmod 640 "$DIR/$STAMP".*
sha256sum "$DIR/$STAMP".*
