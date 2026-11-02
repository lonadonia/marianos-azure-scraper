#!/usr/bin/env bash
# Offline checks of oxylabs-classic-probe 1.6.0 from the clean extraction of MARIANOS_SOURCE_1.8.0rc4.zip.
# No request is sent (the probe's live mode is disabled; its tests close the network).
P=/c/x18/MARIANOS_SOURCE_1.8.0rc4/classic_probe
OUT=C:/m6/ev/probe_x18
export UV_PYTHON='C:\w6\py312\pkg\tools\python.exe'
UV=/c/Users/<user>/.local/bin/uv.exe
cd "$P" || exit 1
step() { echo; echo "### $* ($(date -u +%H:%M:%SZ))"; "$@"; echo "### exit=$?"; }
step "$UV" sync --frozen --offline
step "$UV" run --frozen --offline python -c "import classic_probe; print(classic_probe.__version__)"
step "$UV" run --frozen --offline pytest -q -p no:cacheprovider
step "$UV" run --frozen --offline ruff check src tests
step "$UV" run --frozen --offline ruff format --check src tests
step "$UV" run --frozen --offline mypy
step "$UV" run --frozen --offline classic-probe plan --targets config/targets.json
step "$UV" run --frozen --offline classic-probe validate --targets config/targets.json
rm -rf "$OUT/replay_marianos" "$OUT/ledger"
mkdir -p "$OUT/ledger"
step "$UV" run --frozen --offline classic-probe replay --targets config/targets.json --fixtures tests/captures_marianos --rates config/rates.example.json --out "$OUT/replay_marianos" --retailer marianos
step "$UV" run --frozen --offline classic-probe campaign-init --manifest "$OUT/ledger/manifest.json" --ledger "$OUT/ledger/ledger.jsonl" --campaign-id X18-OFFLINE --offline
step "$UV" run --frozen --offline classic-probe live --manifest "$OUT/ledger/manifest.json"
step "$UV" run --frozen --offline classic-probe status --manifest "$OUT/ledger/manifest.json"
echo "END $(date -u +%H:%M:%SZ)"
