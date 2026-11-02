"""Defects put back, one at a time, into a copy of the source: each must make the page-loop regressions fail.

Usage: mutants.py <output json>. Uses its own database (marianos_mut_test) and a copy of the working tree's src and
tests under C:/m6/mut. The working tree is never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

WT = Path(r"C:\m5\wt\headless\marianos-azure-headless")
MUT = Path(r"C:\m6\mut")
PY = WT / ".venv" / "Scripts" / "python.exe"
OUT = Path(sys.argv[1])

MUTANTS = [
    (
        "a repeated page counts as a page",
        "src/marianos_headless/collection/pagination.py",
        "ACCEPTED = frozenset({PageVerdict.NEW, PageVerdict.PARTIAL_OVERLAP})",
        "ACCEPTED = frozenset({PageVerdict.NEW, PageVerdict.PARTIAL_OVERLAP, PageVerdict.REPEATED, PageVerdict.REORDERED_REPEAT})",
    ),
    (
        "any row of a page counts as completed",
        "src/marianos_headless/collection/pagination.py",
        'by_page = {r.requested_page: r for r in rows if r.state == "completed"}',
        "by_page = {r.requested_page: r for r in rows}",
    ),
    (
        "a failed page closes the listing and the run goes on",
        "src/marianos_headless/collection/oxylabs_live.py",
        '                    self._unread(ctx, node, page, f"the provider brought no page ({exc.kind})")\n                v = self.verify(fetch)\n            view = self._view(fetch)',
        '                    state.status, state.reason = "DONE", ""\n                    break\n                v = self.verify(fetch)\n            view = self._view(fetch)',
    ),
    (
        "the page's store is not checked after page 1",
        "src/marianos_headless/collection/pagination.py",
        "    if not store_verified:\n",
        "    if not store_verified and page == 1:\n",
    ),
    (
        "a resume trusts the task's cursor, not the table",
        "src/marianos_headless/collection/oxylabs_live.py",
        "        done = self._restore(node, state)\n        earlier = [tuple(r.identities or []) for r in done]",
        "        done = self._restore(node, state)[: state.steps_done] if False else []\n        earlier = [tuple(r.identities or []) for r in done]",
    ),
    (
        "the page number the response states is not compared",
        "src/marianos_headless/collection/pagination.py",
        "    if facts.returned_page != page or (facts.loaded_pages and page not in facts.loaded_pages):\n",
        "    if False:\n",
    ),
    (
        "the listing the response states is not compared",
        "src/marianos_headless/collection/pagination.py",
        "    if taxonomy is not None and facts.taxonomy_id != taxonomy:\n",
        "    if False:\n",
    ),
    (
        "the last page ends a listing as DONE whatever was read",
        "src/marianos_headless/collection/pagination.py",
        "    if want is not None and unique >= want:\n",
        "    if want is not None:\n",
    ),
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
        "            abandoned = recovery.recover_abandoned(s, self.store_id, now=now)\n            s.commit()\n        with self.factory() as s:\n            if not self._collection_left(s):",
        "            abandoned = []\n            s.commit()\n        with self.factory() as s:\n            if not self._collection_left(s):",
    ),
]

env = dict(os.environ)
port = Path(r"C:\m6\pg\data\postmaster.pid").read_text().splitlines()[3].strip()
url = f"postgresql+psycopg://postgres:@127.0.0.1:{port}/marianos_mut_test"
env.update(
    MARIANOS_COLLECTOR_TEST_DATABASE_URL=url,
    PSYCOPG_IMPL="python",
    PYTHONPATH=str(MUT / "src"),
    PYTHONUTF8="1",
    PYTHONDONTWRITEBYTECODE="1",
)

setup = (
    "from sqlalchemy import create_engine, text\n"
    f"e = create_engine('postgresql+psycopg://postgres:@127.0.0.1:{port}/postgres', isolation_level='AUTOCOMMIT')\n"
    "c = e.connect()\n"
    "c.execute(text(\"SELECT 1 FROM pg_database WHERE datname='marianos_mut_test'\")).first() or c.execute(text('CREATE DATABASE marianos_mut_test'))\n"
)
subprocess.run([str(PY), "-c", setup], env=env, check=True, cwd=str(WT))

# One snapshot: the working tree may move while this runs.
BASE = Path(r"C:\m6\mutbase")
if BASE.exists():
    shutil.rmtree(BASE)
BASE.mkdir(parents=True)
shutil.copytree(WT / "src", BASE / "src", ignore=shutil.ignore_patterns("__pycache__"))
shutil.copytree(WT / "tests", BASE / "tests", ignore=shutil.ignore_patterns("__pycache__", "captures"))
shutil.copytree(WT / "config", BASE / "config")
shutil.copy(WT / "pyproject.toml", BASE / "pyproject.toml")

results = []
for name, rel, a, b in MUTANTS:
    if MUT.exists():
        shutil.rmtree(MUT)
    MUT.mkdir(parents=True)
    shutil.copytree(BASE / "src", MUT / "src")
    shutil.copytree(BASE / "tests", MUT / "tests")
    shutil.copytree(BASE / "config", MUT / "config")
    shutil.copy(BASE / "pyproject.toml", MUT / "pyproject.toml")
    p = MUT / rel
    t = p.read_bytes().decode("utf-8")
    if t.count(a) != 1:
        results.append({"mutant": name, "error": f"pattern found {t.count(a)} times"})
        OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
        continue
    p.write_bytes(t.replace(a, b).encode("utf-8"))
    started = time.time()
    r = subprocess.run(
        [str(PY), "-X", "utf8", "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "--tb=no",
         "tests/integration/test_listing_pages.py"],
        cwd=str(MUT), env=env, capture_output=True, encoding="utf-8", errors="replace", timeout=900,
    )
    failed = [ln.split(" ")[1].split("::")[-1] for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))]
    last = [ln for ln in r.stdout.splitlines() if " passed" in ln or " failed" in ln][-1:]
    results.append(
        {"mutant": name, "file": rel, "exit": r.returncode, "summary": last, "failed": failed,
         "seconds": round(time.time() - started)}
    )
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
shutil.rmtree(MUT, ignore_errors=True)
print("done", len(results))
