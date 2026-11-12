"""Run one verification command and keep a complete record of it (command, environment, revision, UTC times,
exit code, counts, log hash). A setup error is recorded as NOT RUN, never as a pass.

Usage: python -I runlog.py <label> <cwd> <log dir> -- <command...>
Writes <log dir>/<label>.log (the full output) and <log dir>/<label>.json (the record), and appends the record to
<log dir>/RUNS.jsonl. Environment: only the names of variables that matter are recorded (never values of secrets).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

SHOWN_ENV = ("PSYCOPG_IMPL", "PYTHONUTF8", "UV_PYTHON", "MARIANOS_COLLECTOR_TEST_DATABASE_URL")
SUMMARY = re.compile(
    r"^(?:=+ )?(?P<body>\d+ (?:passed|failed|skipped|errors?|xfailed|xpassed|deselected|warnings?)[^\n]*?)"
    r" in (?P<secs>[\d.]+)s(?: \([^)]*\))?(?: =+)?$",
    re.M,
)


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)
    return r.stdout.strip()


def main() -> int:
    label, cwd, log_dir = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    if sys.argv[4] != "--":
        raise SystemExit("usage: runlog.py <label> <cwd> <log dir> -- <command...>")
    cmd = sys.argv[5:]
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{label}.log"
    if log.exists():
        raise SystemExit(f"{log} exists: a log is never overwritten")
    rev = git(cwd, "rev-parse", "HEAD")
    dirty = git(cwd, "status", "--porcelain", "--untracked-files=no")
    start = datetime.now(UTC)
    with log.open("wb") as fh:
        proc = subprocess.run(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, check=False)
    end = datetime.now(UTC)
    data = log.read_bytes()
    # pytest on Windows writes CRLF: the pattern's line end would never match before a CR (counts were lost).
    text = data.decode("utf-8", "replace").replace("\r\n", "\n")
    counts: dict[str, int] = {}
    m = None
    for m in SUMMARY.finditer(text):
        pass
    if m is not None:
        for part in m.group("body").split(","):
            bits = part.strip().split(" ", 1)
            if len(bits) == 2 and bits[0].isdigit():
                counts[bits[1].strip()] = int(bits[0])
    setup_error = bool(re.search(r"^(ERROR|E) .*(collect|setup|fixture)", text, re.M | re.I)) or (
        "errors" in counts or "error" in counts
    )
    skip_reasons: dict[str, int] = {}
    for sm in re.finditer(r"^SKIPPED \[(\d+)\] [^:]+:\d+: (.*)$", text, re.M):
        skip_reasons[sm.group(2).strip()] = skip_reasons.get(sm.group(2).strip(), 0) + int(sm.group(1))
    rec = {
        "label": label,
        "command": cmd,
        "cwd": str(cwd),
        "revision": rev,
        "worktree_modified_tracked_files": dirty.splitlines(),
        "env": {k: os.environ.get(k, "") for k in SHOWN_ENV if k in os.environ and "URL" not in k}
        | {k: "(set)" for k in SHOWN_ENV if k in os.environ and "URL" in k},
        "host": {"os": platform.platform(), "python_of_runner": sys.version.split()[0]},
        "utc_start": start.isoformat(timespec="seconds"),
        "utc_end": end.isoformat(timespec="seconds"),
        "seconds": round((end - start).total_seconds(), 1),
        "exit_code": proc.returncode,
        "pytest_counts": counts,
        "skip_reasons": skip_reasons,
        "verdict": (
            "NOT RUN (setup/collection error)" if setup_error and not counts.get("passed")
            else "NOT RUN (environment missing: tests skipped for setup)"
            if any("not installed" in r or "no MARIANOS_COLLECTOR_TEST_DATABASE_URL" in r for r in skip_reasons)
            else f"FAIL (exit {proc.returncode})" if proc.returncode != 0
            else f"PASS WITH {counts.get('skipped', 0)} SKIPPED (see skip_reasons)" if counts.get("skipped")
            # a pass is read from the output, never from the exit code alone
            else "PASS" if counts.get("passed") and not counts.get("failed")
            else "UNVERIFIED (exit 0 but no pytest summary line was found)"
        ),
        "log": str(log),
        "log_bytes": len(data),
        "log_sha256": hashlib.sha256(data).hexdigest(),
    }
    (log_dir / f"{label}.json").write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    with (log_dir / "RUNS.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(json.dumps({k: rec[k] for k in ("label", "revision", "utc_start", "utc_end", "seconds", "exit_code",
                                          "pytest_counts", "verdict", "log_sha256")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
