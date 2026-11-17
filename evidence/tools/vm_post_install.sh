#!/usr/bin/env bash
# PRIVATE OPS (owner VM, root; started detached with systemd-run after vm_rc6_install.sh): the two checks of the
# installed candidate that need no provider request, one after the other (heavy jobs never run together):
#   1. OR-20: vm_or20.sh (validate-export --run F2 under a memory bound);
#   2. the container: vm_container.sh as the admin user (docker build from the verified tree, its version and
#      configuration checks, read-only checks against the target database).
# Each step's output goes to $O/post_install.log; ALL_DONE ends it.
set -u
O=/var/lib/marianos-collector/ops-rc6
L="$O/post_install.log"
exec >>"$L" 2>&1
echo "== $(date -u +%FT%TZ) OR-20 (vm_or20.sh)"
bash "$O/vm_or20.sh"; echo "== vm_or20.sh exit $?"
echo "== $(date -u +%FT%TZ) container (vm_container.sh)"
runuser -u "${ADMIN_USER:?}" -- env W="${W:?}" COMMIT="${COMMIT:?}" TAG_VERSION=1.10.0rc6 DB=marianos_rc5 \
  bash "$W/vm_container.sh"; echo "== vm_container.sh exit $?"
echo "== $(date -u +%FT%TZ) ALL_DONE"
