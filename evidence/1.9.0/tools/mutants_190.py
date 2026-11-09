"""The three mutants planned for 1.8.0rc5 and not run then (evidence/tests/regress/mutants.json: 8 of 11 run;
the 9th timed out when the workstation entered standby), run on the 1.9.0 candidate. Same method as
evidence/tools/mutants.py: each defect is put back, alone, into a copy of the candidate's src, tests and config,
and the listing-page regressions (tests/integration/test_listing_pages.py) run against it. A mutant is caught when
at least one test fails. The candidate's own tree is never touched.

The database is the tests' own throwaway PostgreSQL (pgserver), as in the candidate's integration suite.

usage: python -I mutants_190.py CANDIDATE_ROOT WORK_DIR OUT_JSON
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

WT, WORK, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
PY = WT / ".venv" / "Scripts" / "python.exe"
PGBIN = WT / ".venv" / "Lib" / "site-packages" / "pgserver" / "pginstall" / "bin"

# The three mutants of 1.8.0rc5's plan that were not run, word for word (evidence/tools/mutants.py, entries 9-11).
MUTANTS = [
    (
        "a page without its cards counts",
        "src/marianos_headless/collection/pagination.py",
        "    if facts.cards < len(facts.organic):\n",
        "    if False:\n",
    ),
    (
        "a capped page counts as completed",
        "src/marianos_headless/collection/oxylabs_live.py",
        'state_name="capped" if res.capped is not None else "completed",',
        'state_name="completed",',
    ),
    (
        "recovery waits until the account has room",
        "src/marianos_headless/collection/live.py",
        "            abandoned = recovery.recover_abandoned(s, self.store_id, now=now)\n            s.commit()\n"
        "        with self.factory() as s:\n            if not self._collection_left(s):",
        "            abandoned = []\n            s.commit()\n        with self.factory() as s:\n"
        "            if not self._collection_left(s):",
    ),
]
TESTS = sys.argv[4:] or ["tests/integration/test_listing_pages.py"]

env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("OXYLABS", "SCRAPFLY", "MARIANOS_COLLECTOR"))}
env.update(
    PATH=str(PGBIN) + os.pathsep + env.get("PATH", ""),
    PSYCOPG_IMPL="python",
    PYTHONUTF8="1",
    PYTHONDONTWRITEBYTECODE="1",
)
# The candidate's revision and whether its tracked files differ from it, recorded with each result.
REV = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(WT), capture_output=True, text=True, check=True).stdout.strip()
TRACKED_CHANGES = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=str(WT),
                                 capture_output=True, text=True, check=True).stdout.strip()

BASE = WORK / "base"
if WORK.exists():
    shutil.rmtree(WORK)
BASE.mkdir(parents=True)
for d in ("src", "tests", "config"):
    shutil.copytree(WT / d, BASE / d, ignore=shutil.ignore_patterns("__pycache__"))
shutil.copy(WT / "pyproject.toml", BASE / "pyproject.toml")

results = []
# The control: the same tests on the unchanged copy must pass, so that a mutant's failure is the mutant's.
for name, rel, a, b in [("control: the unchanged copy", None, None, None), *MUTANTS]:
    mut = WORK / "mut"
    if mut.exists():
        shutil.rmtree(mut)
    shutil.copytree(BASE, mut)
    if rel is not None:
        p = mut / rel
        t = p.read_bytes().decode("utf-8")
        if t.count(a) != 1:
            results.append({"mutant": name, "file": rel, "error": f"pattern found {t.count(a)} times"})
            OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
            continue
        p.write_bytes(t.replace(a, b).encode("utf-8"))
    run_env = dict(env, PYTHONPATH=str(mut / "src"))
    # The copy's own package must be the one imported (not the candidate's editable install).
    probe = subprocess.run(
        [str(PY), "-c", "import marianos_headless, sys; sys.stdout.write(marianos_headless.__file__)"],
        cwd=str(mut), env=run_env, capture_output=True, text=True, check=True,
    ).stdout
    assert Path(probe).resolve().is_relative_to(mut.resolve()), probe
    started = time.time()
    r = subprocess.run(
        [str(PY), "-X", "utf8", "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "--tb=line", "-rfE",
         *TESTS],
        cwd=str(mut), env=run_env, capture_output=True, encoding="utf-8", errors="replace", timeout=2400,
    )
    lines = r.stdout.splitlines()
    failed = [ln.split(" ")[1] for ln in lines if ln.startswith(("FAILED", "ERROR"))]
    last = [ln for ln in lines if " passed" in ln or " failed" in ln or " error" in ln][-1:]
    # --tb=line: one "path:line: message" line per failure, the evidence of what each failing test saw
    tb = [ln for ln in lines if re.match(r"^[^ ]+\.py:\d+: ", ln)][:20]
    rec = {
        "mutant": name,
        "file": rel,
        "imported_from": "the copy (" + ("unchanged" if rel is None else "mutated") + ")",
        "tests": TESTS,
        "exit": r.returncode,
        "summary": last,
        "failed": failed,
        "failure_lines": tb,
        "seconds": round(time.time() - started),
        "candidate_revision": REV,
        "candidate_tracked_changes": TRACKED_CHANGES or "none",
    }
    if rel is None:
        # the control passes only when every test ran and passed (a skipped database test proves nothing)
        s = last[0] if last else ""
        rec["control_passed"] = (r.returncode == 0 and "passed" in s and "skipped" not in s and "failed" not in s
                                 and "error" not in s)
    else:
        rec["caught"] = r.returncode != 0 and bool(failed)
    results.append(rec)
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps(results[-1])[:400], flush=True)
shutil.rmtree(WORK, ignore_errors=True)
print("done", len(results))
