#!/bin/bash
# One-time preparation of a Linux VM (Ubuntu 24.04) for marianos-collector. Run as root.
#
# Adds only what the collector needs and never removes anything: the OS packages python3.12-venv and
# postgresql, a system user without a login shell, its folders, and a local database owned by a role of
# the same name (peer authentication on the local socket: no password). Every step is skipped when its
# result already exists, so running it again changes nothing. It never drops a database or a role.
set -euo pipefail

SVC_USER="${SVC_USER:-marianos}"
DB_NAME="${DB_NAME:-marianos_collector}"

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 2; }

need=()
dpkg -s python3.12-venv >/dev/null 2>&1 || need+=(python3.12-venv)
dpkg -s postgresql >/dev/null 2>&1 || need+=(postgresql)
if [ "${#need[@]}" -gt 0 ]; then
  apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${need[@]}"
fi

if ! id -u "$SVC_USER" >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/marianos-collector --shell /usr/sbin/nologin "$SVC_USER"
fi

install -d -m 755 -o root -g root /opt/marianos-collector /opt/marianos-collector/releases
install -d -m 750 -o "$SVC_USER" -g "$SVC_USER" /var/lib/marianos-collector \
  /var/lib/marianos-collector/data /var/lib/marianos-collector/backups
install -d -m 750 -o root -g "$SVC_USER" /etc/marianos-collector

if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$SVC_USER'" | grep -q 1; then
  runuser -u postgres -- createuser "$SVC_USER"
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1; then
  runuser -u postgres -- createdb -O "$SVC_USER" "$DB_NAME"
fi

echo "prepared: user $SVC_USER, database $DB_NAME, /opt/marianos-collector, /var/lib/marianos-collector," \
  "/etc/marianos-collector"
