"""T05 reproduction: the probe's offline replay with missing, malformed or invalid saved responses, run against one
probe source tree (1.7.2 to show the defect, 1.7.3 to show the fix). Nothing leaves the machine: the replay is
offline and never reads a credential (credentials come only from the environment, on the live path).

usage: python t05_repro.py PROBE_ROOT PYTHON WORK_DIR
Prints, per case: the probe version, exit code, whether --out was created (and what it holds), whether stderr
holds a traceback, and stderr's last line.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT, PY, WORK = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
TARGETS = ROOT / "config" / "targets.json"
RATES = {
    "synthetic": True,
    "confirmed_by": "SYNTHETIC test rate card",
    "confirmed_at": "2026-10-31",
    "basis": "SYNTHETIC: invented for the offline tests; not this or any account's rates",
    "rates": {
        "walmart_search": {"unit": "usd_per_result", "plain": "0.0015", "rendered": "0.0020"},
        "walmart_product": {"unit": "usd_per_result", "plain": "0.0015", "rendered": "0.0020"},
        "url_only": {"unit": "usd_per_result", "plain": "0.0010", "rendered": "0.0015"},
    },
}
CASES = {
    "missing_replay_json": None,
    "empty_object": "{}",
    "not_json": "{not json",
    "missing_body_file": json.dumps({"steps": {"s1": [{"http_status": 200, "body_file": "absent.json"}]}}),
}

if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir(parents=True)
env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("OXYLABS", "CLASSIC"))}
env["PYTHONPATH"] = str(ROOT / "src")
env["PYTHONUTF8"] = "1"
version = subprocess.run(
    [PY, "-c", "import classic_probe, sys; sys.stdout.write(classic_probe.__version__ + ' ' + classic_probe.__file__)"],
    capture_output=True,
    text=True,
    env=env,
    check=True,
).stdout
print("probe:", version)
for name, content in CASES.items():
    case = WORK / name
    fixtures = case / "fixtures"
    fixtures.mkdir(parents=True)
    if content is not None:
        (fixtures / "replay.json").write_text(content, encoding="utf-8")
    rates = case / "rates.json"
    rates.write_text(json.dumps(RATES), encoding="utf-8")
    out = case / "out"
    cmd = [PY, "-m", "classic_probe", "replay", "--targets", str(TARGETS), "--fixtures", str(fixtures)]
    cmd += ["--rates", str(rates), "--out", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=case, check=False)
    err = r.stderr.strip().splitlines()
    held = sorted(p.name for p in out.iterdir()) if out.exists() else []
    print(
        json.dumps(
            {
                "case": name,
                "exit": r.returncode,
                "out_created": out.exists(),
                "out_holds": held,
                "traceback": "Traceback" in r.stderr,
                "stderr_lines": len(err),
                "stderr_last": err[-1] if err else "",
                "stdout": r.stdout.strip()[:200],
            }
        )
    )
