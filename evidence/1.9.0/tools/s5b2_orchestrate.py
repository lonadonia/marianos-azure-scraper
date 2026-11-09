"""Stage S5b2 of collector 1.9.0rc4 (S5b again on the corrected revision): two listing lanes, interrupted on purpose, through the live stage runner.

Steps (each child is ``live190_run.py`` in its own process group, its output in its own log; the ledger rows of
the stage are the progress measure):
  1. run            until at least 3 submissions of the stage are answered, then Ctrl+Break (expected: exit 75,
                    the run interrupted resumably)
  2. resume         until at least 3 more are answered, then, while it runs:
  3. refused-start  a second ``run`` of the store through a gate refusing every submission (expected: exit 9,
                    refused before any reservation)
  4. hard kill      of the resume (taskkill /F /T): its ledger lease is left to expire; the rows it had in flight
                    become unknown (held) or provably unsent, by the ledger's own recovery
  5. resume         after the lease has expired, to the end of the run
The record (UTC times, exit codes, ledger counts at each step) goes to C:/m8/evidence/live190/s5b2_steps.json.

usage: python -I s5b2_orchestrate.py
"""

from __future__ import annotations

import json
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from observe190 import CAMPAIGN, TRIAL_DIR, trial  # noqa: E402

PY = "C:/m8/qwt/headless/marianos-azure-headless/.venv/Scripts/python.exe"
RUNNER = "C:/m8/live/live190_run.py"
STAGE = "M-S5b2-rows23-26-two-lanes-190rc4-20261109"
STORE = "marianos-53100502-pickup"
RUN_ARGS = ["run", "--store", STORE, "--categories", "23,24,25,26", "--max-credits", "30"]
LOGS = Path("C:/m8/evidence/live190/logs")
OUT = Path("C:/m8/evidence/live190/s5b2_steps.json")
STEPS: list[dict[str, Any]] = []


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def counts() -> dict[str, int]:
    led = trial().open_ledger(TRIAL_DIR, CAMPAIGN)
    out: dict[str, int] = {}
    for r in led.rows(stage_id=STAGE):
        out[r["state"]] = out.get(r["state"], 0) + 1
    return out


def answered() -> int:
    c = counts()
    return c.get("settled", 0) + c.get("unknown", 0)


def save() -> None:
    OUT.write_text(json.dumps({"stage": STAGE, "steps": STEPS}, indent=1) + "\n", encoding="utf-8")


def start(name: str, args: list[str]) -> tuple[subprocess.Popen[bytes], Any]:
    log = (LOGS / f"S5b2_{name}.log").open("wb")
    p = subprocess.Popen([PY, "-I", RUNNER, *args], stdout=log, stderr=subprocess.STDOUT,
                         creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    STEPS.append({"step": name, "utc_start": now(), "pid": p.pid, "args": args, "ledger_before": counts()})
    save()
    return p, log


def wait_progress(p: subprocess.Popen[bytes], target: int, timeout_s: float) -> str:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        if p.poll() is not None:
            return "exited"
        if answered() >= target:
            return "reached"
        time.sleep(3)
    return "timeout"


def finish(p: subprocess.Popen[bytes], log: Any, how: str, timeout_s: float) -> None:
    try:
        code = p.wait(timeout=timeout_s)
        ended = "exited"
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, check=False)
        code = p.wait(timeout=60)
        ended = f"did not exit within {timeout_s:.0f} s: killed"
    log.close()
    STEPS[-1].update({"utc_end": now(), "ended_by": how, "end": ended, "exit_code": code, "ledger_after": counts()})
    save()


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        raise SystemExit(f"{OUT} exists: S5b2 is never repeated before its outcome is read")
    # 1. run, then Ctrl+Break
    p, log = start("1_run", ["run", STAGE, "--", *RUN_ARGS])
    got = wait_progress(p, 3, 20 * 60)
    STEPS[-1]["progress"] = got
    if got == "exited":
        finish(p, log, "itself (ended before 3 submissions were answered)", 5)
        return 0
    p.send_signal(signal.CTRL_BREAK_EVENT)
    STEPS[-1]["signal_utc"] = now()
    finish(p, log, "Ctrl+Break (termination signal)", 300)
    # 2. resume
    base = answered()
    p, log = start("2_resume", ["run", STAGE, "--", "resume", "--store", STORE])
    got = wait_progress(p, base + 3, 20 * 60)
    STEPS[-1]["progress"] = got
    if got == "exited":
        finish(p, log, "itself (ended before 3 more submissions were answered)", 5)
        return 0
    # 3. a second start while it runs, through a gate refusing every submission
    t = now()
    r = subprocess.run([PY, "-I", RUNNER, "refused-start", STAGE, "--", *RUN_ARGS], capture_output=True,
                       timeout=600, check=False)
    (LOGS / "S5b2_3_refused_start.log").write_bytes(r.stdout + r.stderr)
    STEPS.append({"step": "3_refused_start", "utc_start": t, "utc_end": now(), "exit_code": r.returncode,
                  "resume_still_running": p.poll() is None, "ledger_after": counts()})
    save()
    # 4. hard kill of the resume
    before = counts()
    k = subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, text=True, check=False)
    code = p.wait(timeout=120)
    log.close()
    STEPS[-2 if STEPS[-1]["step"] == "3_refused_start" else -1].update(
        {"utc_end": now(), "ended_by": "hard kill (taskkill /F /T)", "exit_code": code, "ledger_at_kill": before,
         "taskkill": k.stdout.strip()[:300]})
    save()
    # 5. wait for the ledger lease to expire (TTL 120 s), then resume to the end
    time.sleep(135)
    p, log = start("5_resume", ["run", STAGE, "--", "resume", "--store", STORE])
    try:
        code = p.wait(timeout=70 * 60)
        ended = "exited"
    except subprocess.TimeoutExpired:
        p.send_signal(signal.CTRL_BREAK_EVENT)
        code = p.wait(timeout=300)
        ended = "stage time limit: Ctrl+Break"
    log.close()
    STEPS[-1].update({"utc_end": now(), "ended_by": ended, "exit_code": code, "ledger_after": counts()})
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
