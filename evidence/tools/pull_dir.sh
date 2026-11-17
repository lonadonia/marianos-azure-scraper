#!/usr/bin/env bash
# PRIVATE (workstation): streams one VM folder (read as root) into LOCAL_PARENT as a .tgz, extracts it, and checks the
# folder's own SHA256SUMS. Usage: pull_dir.sh REMOTE_DIR LOCAL_PARENT
set -euo pipefail
R="$1"; L="$2"; mkdir -p "$L"
name=$(basename "$R"); parent=$(dirname "$R")
bash [redacted:workstation-path]/tools/vm.sh "sudo tar -C '$parent' -czf - '$name'" > "$L/$name.tgz"
tar -C "$L" -xzf "$L/$name.tgz"
( cd "$L/$name" && sha256sum -c --quiet SHA256SUMS && echo "PULLED AND VERIFIED: $L/$name ($(find . -type f | wc -l) files)" )
