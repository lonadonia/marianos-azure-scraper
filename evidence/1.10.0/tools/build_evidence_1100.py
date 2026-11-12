"""Builds evidence/1.10.0/ for the publication of the offline candidate, from the records of task 1.10
(C:/m8/evidence/c1100, C:/m8/logs/tests1100, the development branch marianos-1.10, and a read of the shared trial
ledger; no request is made and nothing is reserved). Each published file is UTF-8 with LF line ends; every change
from its private original (a masked value) is recorded with both SHA-256 in TRANSFORMS.json.

Usage: python -I build_evidence_1100.py DEST_DIR"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# The masking rules and the copy helpers are those of the 1.9 builder (its definitions, read from its file).
_HELPERS = Path("C:/m8/pub/build_evidence_190.py").read_text("utf-8").split("\nif DEST.exists():", 1)[0]
exec(compile(_HELPERS, "build_evidence_190.py (helpers)", "exec"), globals())  # noqa: S102

EV = Path("C:/m8/evidence/c1100")
LOGS = Path("C:/m8/logs/tests1100")
TOOLS = Path("C:/m8/tools")
WT = "C:/m8/wt"
SRC = "headless/marianos-azure-headless"
RC4 = "8abc2c1297b8005d162721b6ddbf66bf8684d548"
CAND = subprocess.run(["git", "rev-parse", "marianos-1.10"], cwd=WT, capture_output=True, text=True, check=True).stdout.strip()
COMMITS = (  # (short name, what, the paths its diff is cut to; None: the whole commit)
    ("454b79d", "C1", None),
    ("8158b49", "NOTES_O1_COUNT", None),
    ("cf3b8eb", "PUBLICATION_RESULT", None),
    ("87086c1", "TESTS_ONLY", None),
    ("a1040f7", "PARSER_VERSION", None),
)
BEFORE, AFTER = "1.9.0rc4", "1.10.0rc3"


def put(rel, data, *, origin, original=None, notes=None, what=""):  # type: ignore[no-redef]
    out = DEST / rel  # noqa: F821
    out.parent.mkdir(parents=True, exist_ok=True)
    b = data.encode("utf-8") if isinstance(data, str) else data
    out.write_bytes(b)
    FILES.append({"published": f"evidence/1.10.0/{rel}", "origin": origin, "sha256": sha(b), "what": what})  # noqa: F821
    if original is not None and notes:
        TRANSFORMS.append(  # noqa: F821
            {"published": f"evidence/1.10.0/{rel}", "original": origin, "original_sha256": sha(original),  # noqa: F821
             "published_sha256": sha(b), "what": "; ".join(notes)}  # noqa: F821
        )


def copy_text(src, rel, *, what="", cp1252_ok=False):  # type: ignore[no-redef]
    """1.9's copy_text, except that Windows line ends written as LF are recorded too (1.9 left them unrecorded)."""
    raw = src.read_bytes()
    notes: list[str] = []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        assert cp1252_ok, f"{src} is not UTF-8"
        bad = sum(1 for x in raw if x >= 0x80)
        assert all(x == 0x9B for x in raw if x >= 0x80), src
        text = raw.decode("cp1252")
        notes.append(f"console byte 0x9B (cp1252 '›') x{bad} written as UTF-8")
    crlf = text.count("\r\n")
    if crlf:
        text = text.replace("\r\n", "\n")
        notes.append(f"Windows line ends (CRLF) written as LF x{crlf}")
    assert "\r" not in text, f"{src}: a lone carriage return"
    text, more = masked(text)  # noqa: F821
    notes += more
    # pytest writes the workstation's computer name into each JUnit result file: not published
    text, n_host = re.subn(r'(?<=\shostname=")[^"<>]+(?=")', "<workstation>", text)
    if n_host:
        notes.append(f"workstation computer name (JUnit hostname attribute) x{n_host}")
    assert "DESKTOP-" not in text.upper(), f"{src}: a computer name left"
    put(rel, text, origin=f"private:{src.as_posix()}", original=raw, notes=notes, what=what)


LINT = {  # the line each check prints when it passes: its verdict is read from that line, never from the exit code
    "ruff_check": re.compile(r"^All checks passed!$", re.M),
    "ruff_format": re.compile(r"^\d+ files already formatted$", re.M),
    "mypy": re.compile(r"^Success: no issues found in \d+ source files$", re.M),
}


def git(*args: str) -> str:
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=WT, capture_output=True, check=True)
    return r.stdout.decode("utf-8")


def text_of(src: Path, rel: str, what: str) -> None:
    copy_text(src, rel, what=what)  # noqa: F821


if DEST.exists():  # noqa: F821
    shutil.rmtree(DEST)  # noqa: F821
DEST.mkdir(parents=True)  # noqa: F821
assert git("status", "--porcelain").strip() == "", "the development worktree has changes"
assert git("rev-parse", "HEAD").strip() == CAND
TREE = git("rev-parse", f"{CAND}:{SRC}").strip()

# --- the two case files, before and after --------------------------------------------------------------------
for folder, stem, title in (("c1", "c1_cases", "C1"), ("publication_result", "publication_cases", "the publication result")):
    before = EV / stem / f"rc4_{'c1_cases' if folder == 'c1' else 'publication_result'}.junit.xml"
    after = EV / stem / f"cand_{'c1_cases' if folder == 'c1' else 'publication_result'}.junit.xml"
    table = DEST / folder / "CASES_BEFORE_AFTER.csv"  # noqa: F821
    r = subprocess.run(
        [SIGNED_PY, "-I", str(TOOLS / "cases_table_1100.py"), str(before), str(after), BEFORE, AFTER, str(table)],  # noqa: F821
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert r.returncode == 0, r.stdout + r.stderr
    print(folder, r.stdout.strip())
    raw = table.read_bytes()
    put(f"{folder}/CASES_BEFORE_AFTER.csv", raw, origin="generated: cases_table_1100.py from the two JUnit result files",
        what=f"{title}: each test's outcome on {BEFORE} and on {AFTER}")  # fmt: skip
    for rev in (BEFORE, AFTER):
        for f in sorted((EV / stem / rev).glob("*.json")):
            text_of(f, f"{folder}/cases/{rev}/{f.name}", f"what the case observed on {rev}, written before it was judged")
    text_of(before, f"{folder}/junit/{BEFORE}.junit.xml", f"the test file's results on {BEFORE}")
    text_of(after, f"{folder}/junit/{AFTER}.junit.xml", f"the test file's results on {AFTER}")

# the test files added to the 1.9.0rc4 checkout: each must be the candidate's own file
overlay = json.loads((EV / "RC4_OVERLAY.json").read_text("utf-8"))
assert overlay["revision"] == RC4 and overlay["tracked_files_modified"] == []
checked = {}
for rel, digest in overlay["untracked_test_files_copied_from_the_candidate"].items():
    blob = subprocess.run(["git", "show", f"{CAND}:{SRC}/{rel}"], cwd=WT, capture_output=True, check=True).stdout
    assert sha(blob) == digest, rel  # noqa: F821
    checked[rel] = digest
overlay["copied_from_revision"] = overlay.pop("candidate_revision")
overlay["verified_against_the_delivered_candidate"] = CAND
overlay["verified"] = (f"each of the {len(checked)} files is byte for byte the file of the delivered candidate {CAND[:7]} "
                       f"(git show); they were copied from {overlay['copied_from_revision'][:7]}, whose test files "
                       f"{CAND[:7]} leaves unchanged")  # fmt: skip
put("c1/RC4_OVERLAY.json", json.dumps(overlay, indent=1) + "\n", origin="generated: the files added to the 1.9.0rc4 checkout",
    what="the test files copied onto the unchanged 1.9.0rc4 checkout for the before runs, with their hashes")  # fmt: skip

# --- the diffs -----------------------------------------------------------------------------------------------
log = git("log", "--reverse", "--format=commit %H%ntree of the collector folder: %x00%H%x00%nDate: %aI%n%n%s%n%n%b%n" + "-" * 78, f"{RC4}..{CAND}")
parts = log.split("\x00")
for i in range(1, len(parts), 2):
    parts[i] = git("rev-parse", f"{parts[i]}:{SRC}").strip()
commits_text = (
    f"The candidate {AFTER} is {BEFORE} ({RC4}, collector tree {git('rev-parse', f'{RC4}:{SRC}').strip()}) and the "
    f"commits below, in order.\nCandidate: {CAND}, collector tree {TREE}.\n\n" + "".join(parts)
)
put("diffs/COMMITS.txt", commits_text, origin=f"generated: git log {RC4[:7]}..{CAND[:7]} (branch marianos-1.10)",
    what="the candidate's commits since 1.9.0rc4, with their messages and trees")  # fmt: skip
prev = RC4
for short, name, _ in COMMITS:
    full = git("rev-parse", short).strip()
    assert git("rev-parse", f"{full}^").strip() == prev, short
    stat = git("diff", "--stat=200", f"--relative={SRC}/", prev, full)
    put(f"diffs/{name}_{short}.stat.txt", stat, origin=f"generated: git diff --stat {prev[:7]} {short}", what=f"{name}: files changed")
    if name == "C1":
        code = git("diff", f"--relative={SRC}/", prev, full, "--", f"{SRC}/src", f"{SRC}/config", f"{SRC}/README.md",
                   f"{SRC}/docs", f"{SRC}/pyproject.toml", f"{SRC}/uv.lock")  # fmt: skip
        put(f"diffs/C1_{short}_source_config_docs.diff", code, origin=f"generated: git diff {prev[:7]} {short} (src, config, docs)",
            what="the C1 change against 1.9.0rc4: source, configuration and documents")  # fmt: skip
        tests = git("diff", f"--relative={SRC}/", prev, full, "--", f"{SRC}/tests", f":(exclude){SRC}/tests/fixtures/*.gz")
        put(f"diffs/C1_{short}_tests.diff", tests, origin=f"generated: git diff {prev[:7]} {short} (tests; the gzip fixtures left out)",
            what="the C1 change against 1.9.0rc4: tests and fixture notes (the seven saved pages are binary files)")  # fmt: skip
    else:
        put(f"diffs/{name}_{short}.diff", git("diff", f"--relative={SRC}/", prev, full),
            origin=f"generated: git diff {prev[:7]} {short}", what=f"{name}: the whole commit")  # fmt: skip
    prev = full
assert prev == CAND
put("diffs/RC4_TO_CANDIDATE.stat.txt", git("diff", "--stat=200", f"--relative={SRC}/", RC4, CAND),
    origin=f"generated: git diff --stat {RC4[:7]} {CAND[:7]}", what="everything since 1.9.0rc4: files changed")  # fmt: skip
num = git("diff", "--numstat", f"--relative={SRC}/", RC4, "454b79d", "--", f"{SRC}/src")
src_add = sum(int(x.split("\t")[0]) for x in num.splitlines() if x.split("\t")[0].isdigit())
src_del = sum(int(x.split("\t")[1]) for x in num.splitlines() if x.split("\t")[1].isdigit())

# --- the test sessions ---------------------------------------------------------------------------------------
SESSIONS = (
    ("rc4_c1_cases", "the C1 cases on 1.9.0rc4 (expected: the controls pass, the C1 cases fail)"),
    ("rc4_publication_result", "the publication-result cases on 1.9.0rc4 (expected: the controls pass, the others fail)"),
    ("cand_unit", "the unit suite on the candidate"),
    ("cand_ruff_check", "ruff check on the candidate"),
    ("cand_ruff_format", "ruff format --check on the candidate"),
    ("cand_mypy", "mypy (strict) on the candidate"),
    ("cand_c1_cases", "the C1 cases on the candidate"),
    ("cand_publication_result", "the publication-result cases on the candidate"),
    ("cand_integration", "the whole integration suite on the candidate, with PostgreSQL"),
    ("x_unit", "the unit suite in a clean extraction of the candidate's tree (git archive), installed from its lock"),
    ("x_c1_cases", "the C1 cases in the clean extraction"),
    ("x_publication_result", "the publication-result cases in the clean extraction"),
    ("x_ruff_check", "ruff check in the clean extraction"),
    ("x_ruff_format", "ruff format --check in the clean extraction"),
    ("x_mypy", "mypy (strict) in the clean extraction"),
)
VERSIONS: dict[str, str] = {}


def tool_version(cwd: str, tool: str) -> str:
    """The version of ruff or mypy in the session's own environment (asked once per environment)."""
    key = f"{cwd}|{tool}"
    if key not in VERSIONS:
        py = Path(cwd) / ".venv" / "Scripts" / "python.exe"
        out = subprocess.run([str(py), "-m", tool, "--version"], cwd=cwd, capture_output=True, text=True, check=True)
        VERSIONS[key] = out.stdout.strip()
    return VERSIONS[key]


rows = []
for label, what in SESSIONS:
    rec = json.loads((LOGS / f"{label}.json").read_text("utf-8"))
    extraction = label.startswith("x_")
    want = "" if extraction else (RC4 if label.startswith("rc4_") else CAND)
    assert rec["revision"] == want, (label, rec["revision"])
    assert extraction or rec["worktree_modified_tracked_files"] == [], label
    text_of(LOGS / f"{label}.log", f"tests/{label}.log", f"{what}: the complete output")
    published_log = (DEST / "tests" / f"{label}.log").read_bytes()  # noqa: F821
    out_text = published_log.decode("utf-8")
    rec["log"] = f"evidence/1.10.0/tests/{label}.log"
    rec["log_sha256_private"] = rec.pop("log_sha256")
    rec["log_sha256_published"] = sha(published_log)  # noqa: F821
    kind = next((k for k in LINT if label.endswith(k)), None)
    verdict = rec["verdict"]
    if kind:
        m = LINT[kind].search(out_text)
        assert m and rec["exit_code"] == 0, (label, out_text[-300:])
        verdict = f"PASS: the output says '{m.group(0)}' (exit 0)"
        rec["verdict_of_the_check"] = verdict
        rec["tool_version"] = tool_version(rec["cwd"] if rec["cwd"] != "." else f"{WT}/{SRC}", kind.split("_")[0])
        rec["verdict_note"] = ("runlog.py reads pytest's summary line only, so its own verdict above says UNVERIFIED "
                               "for this check; the check's verdict is read from the tool's own line in its output")  # fmt: skip
    body, notes = masked(json.dumps(rec, indent=1) + "\n")  # noqa: F821
    put(f"tests/{label}.json", body, origin=f"private:{(LOGS / (label + '.json')).as_posix()}",
        original=(LOGS / f"{label}.json").read_bytes(),
        notes=[*notes, "log path made relative; the published log's hash added"
               + ("; the check's verdict read from its output, and the tool's version, added" if kind else "")],
        what=f"{what}: the record (revision, clean tree, times, counts, verdict)")  # fmt: skip
    tail = out_text.strip().splitlines()[-1][:160]
    rows.append(
        {
            "session": label,
            "what": what,
            "revision": (f"none recorded (not a Git checkout): the clean extraction of {CAND[:7]}, its tree "
                         f"{TREE[:8]} checked file for file in tests/x_tree_check.json") if extraction
                        else rec["revision"],  # fmt: skip
            "tracked_files_modified": "n/a" if extraction else len(rec["worktree_modified_tracked_files"]),
            "utc_start": rec["utc_start"],
            "utc_end": rec["utc_end"],
            "seconds": rec["seconds"],
            "exit_code": rec["exit_code"],
            "verdict": verdict,
            "counts": "; ".join(f"{v} {k}" for k, v in rec["pytest_counts"].items()),
            "skip_reasons": "; ".join(f"{v} x {k}" for k, v in rec["skip_reasons"].items()),
            "last_line_of_the_log": tail,
            "environment": "; ".join(f"{k}={v}" for k, v in rec["env"].items()),
        }
    )
for name, identical, what in (
    ("x_tree_check_first_extraction", False,
     "the first extraction (git archive under the workstation's core.autocrlf=true, the repository's '* -text' being "
     "outside the archived folder): line ends differed in 203 of 265 files; replaced before any session ran in it"),
    ("x_tree_check_before_install", True, "the extraction made again with core.autocrlf=false, before its install"),
    ("x_tree_check", True, "the clean extraction after its install from the lock (uv sync --frozen --offline), "
                           "before its sessions ran"),
    ("x_tree_check_after_sessions", False,
     "the clean extraction after its sessions ran: no file of the tree missing or changed; 79 files added, all under "
     ".hypothesis/ (the example database Hypothesis writes when the unit suite's property tests run), a folder this "
     "check does not leave aside as it does the caches"),
):  # fmt: skip
    xtree = json.loads((LOGS / f"{name}.json").read_text("utf-8"))
    assert xtree["identical"] is identical and xtree["tree"] == TREE, name
    if name == "x_tree_check_first_extraction":
        assert len(xtree["different"]) == 203 and not xtree["missing"] and not xtree["extra"], name
    elif name == "x_tree_check_after_sessions":
        assert not xtree["missing"] and not xtree["different"] and len(xtree["extra"]) == 79, name
        assert all(x.startswith(".hypothesis/") for x in xtree["extra"]), name
    text_of(LOGS / f"{name}.json", f"tests/{name}.json", what)
first = LOGS / "first_attempt_87086c1"
assert sorted(p.name for p in first.iterdir()) == sorted(f"cand_{n}.{e}" for n in ("unit", "ruff_check", "ruff_format", "mypy")
                                                          for e in ("json", "log"))  # fmt: skip
for f in sorted(first.iterdir()):
    assert json.loads((first / (f.stem + ".json")).read_text("utf-8"))["revision"].startswith("87086c1")
    text_of(f, f"tests/first_attempt_87086c1/{f.name}",
            "the first attempt on 1.10.0rc2 (87086c1): the unit suite 493 passed and 1 failed (the parser version, "
            "corrected in 1.10.0rc3); ruff, format and mypy as their logs say")  # fmt: skip
sup = LOGS / "_superseded"
assert sorted(p.name for p in sup.iterdir()) == ["RUNS.jsonl", "rc4_c1_cases.json", "rc4_c1_cases.log",
                                                 "rc4_publication_result.json", "rc4_publication_result.log"]  # fmt: skip
for f in sorted(sup.iterdir()):
    if f.suffix == ".json":
        assert json.loads(f.read_text("utf-8"))["revision"] == RC4, f
    text_of(f, f"tests/superseded_tests_of_cf3b8eb/{f.name}",
            "the first runs of the before-cases on 1.9.0rc4, with the test files of cf3b8eb (the same counts: 21 failed "
            "and 7 passed; 3 failed and 3 passed); superseded once 87086c1 made three staged cases write their "
            "observation before their first check, since on 1.9.0rc4 they had left none")  # fmt: skip
buf = io.StringIO()
w = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
w.writeheader()
w.writerows(rows)
put("tests/SESSIONS.csv", buf.getvalue(), origin="generated: the sessions' records", what="every test session of this publication")
integ = ET.parse(EV / "cand_integration.junit.xml").getroot()
text_of(EV / "cand_integration.junit.xml", "tests/cand_integration.junit.xml", "the integration suite's result, test by test")
per_file: dict[str, list[int]] = {}
for case in integ.iter("testcase"):
    key = str(case.get("classname") or "").rsplit(".", 1)[-1]
    slot = per_file.setdefault(key, [0, 0, 0])
    slot[0] += 1
    slot[1] += 1 if (case.find("failure") is not None or case.find("error") is not None) else 0
    slot[2] += 1 if case.find("skipped") is not None else 0
buf = io.StringIO()
w2 = csv.writer(buf, lineterminator="\n")
w2.writerow(["test_file", "tests", "failed_or_error", "skipped"])
for key in sorted(per_file):
    w2.writerow([key, *per_file[key]])
put("tests/INTEGRATION_BY_FILE.csv", buf.getvalue(), origin="generated: from the integration suite's JUnit result file",
    what="the integration suite on the candidate, per test file")  # fmt: skip

# --- the coupon examples -------------------------------------------------------------------------------------
text_of(EV / "COUPON_EVIDENCE_CHECK.json", "coupons/COUPON_EVIDENCE_CHECK.json",
        "the client's four coupon examples in the saved source evidence (no request made)")  # fmt: skip

# --- tools ---------------------------------------------------------------------------------------------------
for name, what in (
    ("runlog.py", "runs a test session and records its revision, clean tree, counts and log hash"),
    ("cases_table_1100.py", "the before/after table from two JUnit result files"),
    ("make_fixtures_1100.py", "the fixtures of tests/fixtures/oxylabs_2026-11-09 from the stored pages of 2026-11-09"),
    ("coupon_check_1100.py", "the four coupon examples checked in the saved evidence"),
    ("tree_check_1100.py", "a folder checked file for file against a Git tree (the clean extraction)"),
    ("run_x_sessions_1100.sh", "the x_ sessions, one after the other, in the clean extraction"),
):
    text_of(TOOLS / name, f"tools/{name}", what)

# --- the shared trial ledger: read only ----------------------------------------------------------------------
def ledger(*args: str) -> str:
    return subprocess.run([SIGNED_PY, "-I", str(LEDGER_DIR / "oxytrial_ledger.py"), "--campaign",  # noqa: F821
                           "oxylabs-trial-20261103", *args], capture_output=True, text=True, check=True).stdout  # fmt: skip


status = json.loads(ledger("status"))
chain = ledger("verify-chain").strip()
stages = [s for s in status.pop("stages") if s.get("project") == "marianos"]
summary = {
    "what": "a read of the shared trial ledger at publication time; this task made no request and no reservation",
    "read_at": status["read_at"],
    "verify_chain": chain,
    "campaign": status,
    "marianos_stages": len(stages),
    "last_marianos_stage_closed": max((s.get("closed_at") or "" for s in stages), default=""),
}
body, notes = masked(json.dumps(summary, indent=1, ensure_ascii=False) + "\n")  # noqa: F821
put("budget/LEDGER_STATUS.json", body, origin="generated: oxytrial_ledger.py status / verify-chain (read only)",
    what="the shared trial ledger as read for this publication: unchanged by it")  # fmt: skip

BUILD = DEST.parent / "_build_evidence_1100"  # noqa: F821
BUILD.mkdir(exist_ok=True)
(BUILD / "TRANSFORMS.json").write_text(json.dumps(TRANSFORMS, indent=1) + "\n", "utf-8")  # noqa: F821
(BUILD / "FILES.json").write_text(json.dumps(FILES, indent=1) + "\n", "utf-8")  # noqa: F821
facts = {
    "CAND": CAND, "CAND_TREE": TREE, "C1_SRC_ADDED": src_add, "C1_SRC_DELETED": src_del,
    "LEDGER_READ": status["read_at"], "CHAIN": chain,
    "INTEGRATION": next(r for r in rows if r["session"] == "cand_integration"),
    "SESSIONS": {r["session"]: r["counts"] for r in rows},
}  # fmt: skip
(BUILD / "FACTS.json").write_text(json.dumps(facts, indent=1) + "\n", "utf-8")
print(len(FILES), "files;", len(TRANSFORMS), "transformed; candidate", CAND[:7], "tree", TREE[:8], "; chain:", chain[:60])  # noqa: F821
