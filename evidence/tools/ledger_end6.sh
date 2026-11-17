#!/usr/bin/env bash
# PRIVATE (workstation): the ledger folder of the 1.10.0rc6 delivery, after its last stage has closed. No provider
# request. On the VM: refuses while a marianos-* unit is active or a stage of the ledger is open; runs
# ledger_folder6.py as the ledger's owner (read only) into ops-rc6/ledger_end/ledger; then pulls it to ev/ledger_end/
# (its own SHA256SUMS checked), checks the hash chain of the unmasked EVENTS.csv (every event recomputed), reads the
# ledger's own status (LEDGER_STATUS_END.json) and places the folder in pub6/pre/evidence/ledger/ with
# PEAK_IN_FLIGHT.txt (the in-flight count over every R7 folder). The published copy is masked later by the delivery's
# sanitizer (the credential fingerprint), and its chain is checked again there.
#   ledger_end6.sh R7_FOLDER...      (e.g. R7a R7b R7w R7c R7d R7e)
set -euo pipefail
cd [redacted:workstation-path]
[ $# -ge 1 ] || { echo "usage: ledger_end6.sh R7_FOLDER..."; exit 2; }
OUT="${OUT:-ev/ledger_end}"
PUB="${PUB:-pub6/pre/evidence/ledger}"
W="${W:-/var/lib/marianos-collector/ops-rc6/ledger_end}"
L=/var/lib/oxylabs-marianos-20261116/ledger.sqlite3
[ ! -e "$OUT" ] || { echo "REFUSED: $OUT exists"; exit 2; }
[ ! -e "$PUB" ] || { echo "REFUSED: $PUB exists"; exit 2; }
for f in "$@"; do [ -d "ev/$f" ] || { echo "REFUSED: no folder ev/$f"; exit 2; }; done
T=[redacted:workstation-path]/ledger_end
rm -rf "$T"; mkdir -p "$T/stage"
cp ops6/ledger_folder6.py "$T/stage/"
( cd "$T/stage" && sha256sum ledger_folder6.py ) > "$T/stage/STAGED.sha256"
echo "== $(date -u +%FT%TZ) the ledger folder on the VM"
tar -cf - -C "$T" stage | VM_STDIN=1 bash tools/vm.sh "set -euo pipefail
  n=\$(systemctl list-units 'marianos-*' --state=active,activating,deactivating --no-legend --plain | wc -l)
  [ \"\$n\" = 0 ] || { echo \"REFUSED: \$n marianos unit(s) active\"; systemctl list-units 'marianos-*' --no-legend --plain; exit 3; }
  open=\$(sudo -u marianos python3.12 -I -c \"import sqlite3; c = sqlite3.connect('file:$L?mode=ro', uri=True); print(c.execute('SELECT count(*) FROM stages WHERE closed_at IS NULL').fetchone()[0])\")
  [ \"\$open\" = 0 ] || { echo \"REFUSED: \$open stage(s) of the ledger still open\"; exit 3; }
  sudo test ! -e $W || { echo 'REFUSED: $W exists'; exit 3; }
  D=\$(mktemp -d); trap 'rm -rf \$D' EXIT
  tar -xf - -C \$D; cd \$D/stage; sha256sum -c --quiet STAGED.sha256
  sudo install -d -o marianos -g marianos -m 0700 $W
  sudo install -o marianos -g marianos -m 0600 ledger_folder6.py $W/ledger_folder6.py
  sudo -u marianos python3.12 -I $W/ledger_folder6.py $L $W/ledger"
echo "== $(date -u +%FT%TZ) pull"
mkdir -p "$OUT"
bash tools/vm.sh "sudo tar -cf - -C $W ledger" | tar -xf - -C "$OUT"
( cd "$OUT/ledger" && sha256sum -c --quiet SHA256SUMS ) && echo "pulled: $(grep -c . "$OUT/ledger/SHA256SUMS") files, their SHA256SUMS hold"
echo "== the hash chain of the unmasked event log"
python -I ops6/verify_ledger_chain.py "$(cygpath -m "$OUT/ledger/EVENTS.csv")" | tr -d '\r' > "$OUT/CHAIN_CHECK_PRIVATE.txt"
tail -3 "$OUT/CHAIN_CHECK_PRIVATE.txt"
echo "== the ledger's own status"
bash tools/vm.sh "sudo mstage6 ledger-status" | tr -d '\r' > "$OUT/LEDGER_STATUS_END.json"
python -I -c "import json, sys; d = json.load(open(sys.argv[1], encoding='utf-8')); print(json.dumps(d)[:600])" "$(cygpath -m "$OUT/LEDGER_STATUS_END.json")"
echo "== requests in flight at once over: $*"
FOLDERS=(); for f in "$@"; do FOLDERS+=("ev/$f"); done
python -I ops/peak_in_flight.py "$(cygpath -m "$OUT/PEAK_IN_FLIGHT.txt")" "${FOLDERS[@]}" | tail -4
mkdir -p "$PUB"
cp "$OUT"/ledger/*.csv "$PUB/"
cp "$OUT/LEDGER_STATUS_END.json" "$OUT/PEAK_IN_FLIGHT.txt" "$PUB/"
echo "placed in $PUB: $(ls "$PUB" | tr '\n' ' ')"
echo "== $(date -u +%FT%TZ) done"
