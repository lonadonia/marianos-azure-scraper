#!/usr/bin/env bash
# PRIVATE (workstation): after the walkthrough slice R7w has ended (its recorder unit marianos-walk-r7w no longer
# active): the recording rendered to video on the VM, then the recording, its steps, the raw outputs and the video
# pulled to ev/R7w_walk/ (SHA-256 checked against the VM's) and placed in pub6/pre/evidence/walkthrough/ (raw_r7w/
# published as raw/). No provider request. The walk folder is root's: root copies the recording into a temporary
# folder of the admin user, who renders it (render_cast.py with the installed release's Python and the admin's
# Playwright Chromium, as tested on 2026-11-17); root installs the video beside the recording.
#   walk_render6.sh
set -euo pipefail
cd [redacted:workstation-path]
OUT="${OUT:-ev/R7w_walk}"
PUB="${PUB:-pub6/pre/evidence/walkthrough}"
[ ! -e "$OUT" ] || { echo "REFUSED: $OUT exists"; exit 2; }
[ ! -e "$PUB" ] || { echo "REFUSED: $PUB exists"; exit 2; }
WALK="${WALK:-/var/lib/marianos-collector/ops-rc6/walk}"   # another folder only for a test
T=[redacted:workstation-path]/walk_render
rm -rf "$T"; mkdir -p "$T/stage"
cp ops/render_cast.py "$T/stage/"
( cd "$T/stage" && sha256sum render_cast.py ) > "$T/stage/STAGED.sha256"
echo "== $(date -u +%FT%TZ) render on the VM"
[ "$(bash tools/vm.sh "systemctl is-active marianos-walk-r7w 2>/dev/null || true" | tr -d '\r')" != "active" ] \
  || { echo "REFUSED: the recorder unit is still active"; exit 2; }
# Chromium and the collector would share the VM's memory (3.9 GB): no collector, recorder or stopper unit may run.
busy=$(bash tools/vm.sh "systemctl list-units 'marianos-*' --state=active,activating,deactivating --no-legend --plain | wc -l" | tr -d '\r')
[ "$busy" = "0" ] || { echo "REFUSED: $busy marianos unit(s) active on the VM"; exit 2; }
tar -cf - -C "$T" stage | VM_STDIN=1 bash tools/vm.sh "set -euo pipefail
  D=\$(mktemp -d); trap 'rm -rf \$D' EXIT
  tar -xf - -C \$D; cd \$D/stage; sha256sum -c --quiet STAGED.sha256
  sudo test -s $WALK/walkthrough_r7w.cast; sudo test -d $WALK/raw_r7w; sudo test -s $WALK/steps_r7w.json
  sudo test ! -e $WALK/walkthrough_r7w.webm
  sudo cp $WALK/walkthrough_r7w.cast in.cast; sudo chown \$(id -u):\$(id -g) in.cast
  /opt/marianos-collector/current/venv/bin/python -I render_cast.py in.cast walkthrough_r7w.webm
  cmp -s in.cast <(sudo cat $WALK/walkthrough_r7w.cast)
  sudo install -o root -g root -m 0640 walkthrough_r7w.webm $WALK/walkthrough_r7w.webm
  ls -l walkthrough_r7w.webm | awk '{print \"video bytes:\", \$5}'"
echo "== $(date -u +%FT%TZ) pull"
mkdir -p "$OUT/files"
bash tools/vm.sh "sudo tar -cf - -C $WALK walkthrough_r7w.cast walkthrough_r7w.webm steps_r7w.json raw_r7w" \
  | tar -xf - -C "$OUT/files"
bash tools/vm.sh "sudo sh -c 'cd $WALK && find walkthrough_r7w.cast walkthrough_r7w.webm steps_r7w.json raw_r7w -type f -print0 | sort -z | xargs -0 sha256sum'" \
  | tr -d '\r' > "$OUT/VM_SHA256SUMS.txt"
( cd "$OUT/files" && sha256sum -c --quiet ../VM_SHA256SUMS.txt ) && echo "pulled: $(grep -c . "$OUT/VM_SHA256SUMS.txt") files, hashes equal the VM's"
mkdir -p "$PUB/raw"
cp "$OUT/files/walkthrough_r7w.cast" "$OUT/files/walkthrough_r7w.webm" "$OUT/files/steps_r7w.json" "$PUB/"
cp -r "$OUT/files/raw_r7w/." "$PUB/raw/"
echo "placed in $PUB: $(find "$PUB" -type f | wc -l) files"
echo "== $(date -u +%FT%TZ) done"
