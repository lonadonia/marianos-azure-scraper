"""Stages the 1.10.0rc3 publication in the staging clone (C:/m7/repo) from its clean main at the 1.9.0rc4 delivery.
Nothing is committed here.

Usage: python -I publish_1100.py VALUES_JSON

VALUES_JSON holds the measured results that fill the documents' placeholders (@@NAME@@). Placeholders are filled in
Markdown and JSON text only; a CSV is written by its own script from values given before it is written. The script
refuses to finish while any placeholder is left, while a CSV has an uneven row, or while a file outside the listed
changes differs from the published 1.9.0rc4 delivery."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path("C:/m7/repo")
PUB = Path("C:/m8/pub1100")
PUB190 = Path("C:/m8/pub")
STAGE = Path("C:/m8/pub1100/stage")  # build_evidence_1100.py output: STAGE/evidence/1.10.0 and STAGE/evidence/_build_evidence_1100
WT, SRC = "C:/m8/wt", "headless/marianos-azure-headless"
REL, REL_TREE = "a1040f79919b8e876e0b69cd909cecf9363780b4", "22ebcf96cdb2021347f0e0e4d7506ad4c36d2c10"
RC4, RC4_TREE = "8abc2c1297b8005d162721b6ddbf66bf8684d548", "7a4dfa05e526bddefdfeab9777b9616890e129ea"
P173, P173_TREE = "95f96a02329bd3a92c9c8b07dd53e53ae89fe553", "912801d038092bc84906f6e0c5507388980fb9d8"
BASE = "039fb14fa20ce31734660159f0b9c56bc3f296cb"
SIGNED_PY = "C:/w6/py312/pkg/tools/python.exe"
V = json.loads(Path(sys.argv[1]).read_text("utf-8"))
V.update({"CAND": REL, "CANDS": REL[:7], "CAND_TREE": REL_TREE, "CAND_TREE_SHORT": REL_TREE[:8]})
TAG = V["TAG"]
WRITTEN: list[Path] = []


def git(*args: str, cwd: Path | str = REPO, binary: bool = False) -> str | bytes:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode("utf-8").strip()


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def fill(text: str) -> str:
    for k, v in V.items():
        text = text.replace(f"@@{k}@@", str(v))
    return text


def write(rel: str, text: str) -> None:
    p = REPO / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(fill(text).replace("\r\n", "\n").encode("utf-8"))
    WRITTEN.append(p)


def read(rel: str) -> str:
    return (REPO / rel).read_bytes().decode("utf-8")


def run_py(*args: str) -> None:
    subprocess.run([SIGNED_PY, "-I", *args], check=True)


def even_csv(rel: str) -> None:
    rows = list(csv.reader(io.StringIO(read(rel))))
    assert len({len(r) for r in rows}) == 1, f"{rel}: uneven rows"


# --- 0. preconditions -------------------------------------------------------------------------------------------
assert git("rev-parse", "HEAD") == BASE, "the staging clone is not at the 1.9.0rc4 delivery"
assert git("rev-parse", "origin/main") == BASE, "origin/main moved: fetch and re-inspect first"
assert git("status", "--porcelain") == "", "the staging clone has changes"
assert git("rev-parse", "HEAD:source") == RC4_TREE
assert git("rev-parse", "marianos-1.10", cwd=WT) == REL and git("status", "--porcelain", cwd=WT) == ""
assert git("rev-parse", f"{REL}:{SRC}", cwd=WT) == REL_TREE
old_files = set(git("ls-files").splitlines())
old_blobs = {f: sha((REPO / f).read_bytes()) for f in old_files}
# 1.9's unrecorded line-end conversions, measured on the clone as 1.9 left it (DOC_CORRECTIONS.md)
LE_JSON = STAGE / "LINE_ENDS_190.json"
run_py(str(PUB / "line_ends_190_1100.py"), str(REPO), str(LE_JSON))
LE = json.loads(LE_JSON.read_text("utf-8"))
assert LE["summary"]["line_ends_converted_without_a_record"] == 85 and LE["summary"]["of_which_lf_back_to_crlf_exact"] == 81
assert LE["summary"]["of_which_named_by_their_run_manifest"] == 50 and LE["summary"]["rows_1.8_archive_matching"] == 596
LE_BY_PATH = {f["published"]: f for f in LE["files"]}


# --- 1. source/: the candidate's development tree, byte for byte ------------------------------------------------
def extract(cwd: str, treeish: str, dest: str) -> list[str]:
    tar_bytes = git("-c", "core.autocrlf=false", "archive", "--format=tar", treeish, cwd=cwd, binary=True)
    target = REPO / dest
    if target.exists():
        shutil.rmtree(target)
    executables = []
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tf:  # type: ignore[arg-type]
        for m in tf.getmembers():
            if m.isdir() or m.name == "pax_global_header":
                continue
            assert m.isfile(), m.name
            out = target / m.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(tf.extractfile(m).read())  # type: ignore[union-attr]
            if m.mode & 0o111:
                executables.append(f"{dest}/{m.name}")
    return executables


subprocess.run(["git", "rm", "-r", "-q", "--cached", "source"], cwd=REPO, check=True)
exe = extract(WT, f"{REL}:{SRC}", "source")
git("add", "-f", "-A", "source")
for e in exe:
    git("update-index", "--chmod=+x", e)
assert git("write-tree", "--prefix=source/") == REL_TREE, "source/ is not the development tree of 1.10.0rc3"
assert git("write-tree", "--prefix=classic-probe-1.7.3/") == P173_TREE, "classic-probe-1.7.3/ changed"
print("source/ tree identical:", REL_TREE[:8], "executables:", len(exe))

# --- 2. evidence/1.10.0 -----------------------------------------------------------------------------------------
ev = REPO / "evidence" / "1.10.0"
assert not ev.exists()
shutil.copytree(STAGE / "evidence" / "1.10.0", ev)
write("evidence/1.10.0/README.md", (PUB / "EVIDENCE_1100_README.md").read_text("utf-8"))
write("evidence/1.10.0/REPRODUCE.md", (PUB / "REPRODUCE_1100.md").read_text("utf-8"))
write("evidence/1.10.0/QUALIFICATION_EVIDENCE_REQUIREMENTS.md",
      (PUB / "QUALIFICATION_EVIDENCE_REQUIREMENTS.md").read_text("utf-8"))  # fmt: skip
ns = fill((PUB / "NEXT_STAGES_1100.json").read_text("utf-8"))
json.loads(ns)
write("evidence/1.10.0/budget/NEXT_STAGES.json", ns)
write("evidence/1.10.0/corrections/LINE_ENDS_190.json", LE_JSON.read_text("utf-8"))
# The publication's own scripts, copied byte for byte (never filled: their placeholder names are code).
VERBATIM: set[Path] = set()
for name in ("build_evidence_1100.py", "make_values_1100.py", "line_ends_190_1100.py", "update_matrix_1100.py",
             "make_audit29_1100.py", "make_outstanding_1100.py", "patch_docs_1100.py", "publish_1100.py"):  # fmt: skip
    raw = (PUB / name).read_bytes()
    assert b"\r" not in raw and not re.search(rb"Users[\\/]+PC|contests[\\/]+8", raw), name
    out = REPO / "evidence" / "1.10.0" / "tools" / name
    out.write_bytes(raw)
    VERBATIM.add(out)
    WRITTEN.append(out)

# --- 3. review --------------------------------------------------------------------------------------------------
write("review/TECHNICAL_REPORT_1.10.0.md", (PUB / "TECHNICAL_REPORT_1.10.0.md").read_text("utf-8"))
facts_csv = PUB / "stage" / "csv_facts.json"
facts_csv.write_text(json.dumps({"suites": V["SUITES_WORDS"], "ledger_line": V["LEDGER_LINE"]}), "utf-8")
run_py(str(PUB / "update_matrix_1100.py"), str(REPO / "review" / "ACCEPTANCE_MATRIX.csv"), str(facts_csv))
run_py(str(PUB / "make_audit29_1100.py"), str(REPO / "review" / "AUDIT_29_RECONCILIATION.csv"), str(facts_csv))
run_py(str(PUB / "make_outstanding_1100.py"), str(REPO / "review" / "ACCEPTANCE_MATRIX.csv"),
       str(REPO / "review" / "OUTSTANDING_REQUIREMENTS_1.10.0.csv"))  # fmt: skip
for rel in ("review/ACCEPTANCE_MATRIX.csv", "review/AUDIT_29_RECONCILIATION.csv",
            "review/OUTSTANDING_REQUIREMENTS_1.10.0.csv"):  # fmt: skip
    even_csv(rel)
    assert "@@" not in read(rel), rel
    WRITTEN.append(REPO / rel)  # written by their scripts, not filled
run_py(str(PUB / "patch_docs_1100.py"), str(REPO), TAG)
for rel in ("review/ACCEPTANCE_RUNBOOK.md", "review/SHARED_CLASSIC_PROBE.md", "review/TECHNICAL_REPORT_1.9.0.md",
            "review/COST_AND_RUNTIME_REPORT.md", "review/TECHNICAL_REPORT.md"):  # fmt: skip
    write(rel, read(rel))

# --- 4. front page and evidence index ---------------------------------------------------------------------------
write("README.md", (PUB / "README_1100.md").read_text("utf-8"))
idx = read("evidence/README.md")
anchor = "## Release 1.9 (2026-11-06 to 2026-11-09)\n"
assert idx.count(anchor) == 1, "the evidence index's 1.9 heading"
idx = idx.replace(anchor, (
    "## Release 1.10 (@@DATE@@): the offline C1 candidate\n\n"
    "[`1.10.0/`](1.10.0/README.md): the C1 cases and the publication-result cases on 1.9.0rc4 and on 1.10.0rc3 (each\n"
    "test's outcome and observation on both), the diffs since 1.9.0rc4, the test sessions of the candidate, the coupon\n"
    "examples checked in the saved sources, the proposed stages S6 and S6b (not approved) and what the later live\n"
    "evidence must contain. Nothing in it is live.\n\n"
) + anchor)
write("evidence/README.md", idx)

# --- 5. manifests -----------------------------------------------------------------------------------------------
def sums_of(folder: str) -> str:
    lines = []
    for p in sorted((REPO / folder).rglob("*")):
        if p.is_file():
            lines.append(f"{sha(p.read_bytes())}  {p.relative_to(REPO).as_posix()}")
    return "\n".join(lines) + "\n"


write("manifests/original/MARIANOS_SOURCE_1.10.0rc3.SHA256SUMS.txt", sums_of("source"))
chk = (PUB190 / "check_frozen_trees_190.py").read_text("utf-8")
for old, new in (
    ("- source/               collector 1.9.0rc4 (MARIANOS_SOURCE_1.9.0rc4.SHA256SUMS.txt);",
     "- source/               collector 1.10.0rc3 (MARIANOS_SOURCE_1.10.0rc3.SHA256SUMS.txt);"),
    ('("source/", ORIG / "MARIANOS_SOURCE_1.9.0rc4.SHA256SUMS.txt", "source/"),',
     '("source/", ORIG / "MARIANOS_SOURCE_1.10.0rc3.SHA256SUMS.txt", "source/"),'),
    (f'"source": "{RC4_TREE}",', f'"source": "{REL_TREE}",'),
):
    assert chk.count(old) == 1, old
    chk = chk.replace(old, new)
write("manifests/check_frozen_trees.py", chk)

dc = read("manifests/DOC_CORRECTIONS.md")
head, rest = dc.split("\n", 1)
assert rest.lstrip("\n").startswith("## Release 1.9.0rc4"), "DOC_CORRECTIONS.md layout"
write("manifests/DOC_CORRECTIONS.md", head + "\n\n" + (PUB / "DOC_CORRECTIONS_1100_SECTION.md").read_text("utf-8")
      + rest.lstrip("\n"))  # fmt: skip

build = STAGE / "evidence" / "_build_evidence_1100"
transforms = json.loads((build / "TRANSFORMS.json").read_text("utf-8"))
red = read("manifests/REDACTIONS.csv").rstrip("\n").split("\n")
buf = io.StringIO()
w = csv.writer(buf, lineterminator="\n")
for t in transforms:
    pub_bytes = (REPO / t["published"]).read_bytes()
    assert sha(pub_bytes) == t["published_sha256"], t["published"]
    w.writerow([t["published"], t["original"].replace("private:C:/m8/", "task-1.10:"), t["original_sha256"],
                t["published_sha256"], t["what"]])  # fmt: skip
for f in LE["files"]:  # 1.9's files whose line ends were converted without a record (DOC_CORRECTIONS.md)
    assert sha((REPO / f["published"]).read_bytes()) == f["published_sha256"], f["published"]
    w.writerow([f["published"], f["origin"], f["original_sha256"], f["published_sha256"],
                f"Windows line ends (CRLF) written as LF x{f['crlf']}, in 1.9; recorded in 1.10 (DOC_CORRECTIONS.md); "
                + ("each LF written back as CRLF gives the original"
                   + (", the file its run's exports/manifest.json names" if f.get("run_manifest_names_the_original") else "")
                   if f["lf_written_back_as_crlf_gives_the_original"]
                   else f"the original also holds {f['bare_lf_in_original']} bare LF")])  # fmt: skip
write("manifests/REDACTIONS.csv", "\n".join(red) + "\n" + buf.getvalue())
even_csv("manifests/REDACTIONS.csv")

pub_old = json.loads(read("manifests/PUBLICATION.json"))
pub_new = {
    "repository": "https://github.com/lonadonia/marianos-azure-scraper",
    "review_tag": TAG,
    "packaging_commit": "the commit named by the review tag (a file cannot hold the id of the commit that adds it)",
    "parent_commit": BASE,
    "status": "offline candidate for review: change C1 implemented and proved offline; no live result for this "
              "revision; named milestones still pending. Not a final release, not accepted by the client, not "
              "production",
    "prepared_by": "Hamza",
    "prepared_on": V["DATE"],
    "collector": {
        "name": "marianos-azure-headless", "version": "1.10.0rc3", "development_commit": REL,
        "development_tree": REL_TREE, "development_branch": "marianos-1.10 (local; its history is not published; "
        "the commits since 1.9.0rc4 are listed in evidence/1.10.0/diffs/COMMITS.txt)",
        "published_at": f"source/ (the same Git tree: git rev-parse {TAG}:source)",
        "change_since_1.9.0rc4": f"git diff review-1.9.0rc4-20261109 {TAG} -- source",
        "live_runs": "none: an offline candidate. No request was sent for 1.10 (no provider, retailer, trial "
                     "credit, client account, VM or SSH)",
    },
    "classic_probe": {
        "pinned": {"version": "1.7.3", "development_commit": P173, "development_tree": P173_TREE,
                   "published_at": "classic-probe-1.7.3/ (unchanged since 1.9.0rc4)", "live_mode": "disabled"},
        "linked_not_pinned": {"version": "1.7.4", "published_by": "the Walmart project",
                              "at": "https://github.com/lonadonia/walmart-azure-scraper/tree/"
                                    "review-1.6.8-probe174-20261111/classic-probe-1.7.4",
                              "tree": "07477cc61b2c1aa0871fb17965b132c131314fc6"},
        "frozen": {"version": "1.6.0", "published_at": "classic-probe/ (unchanged since 1.8.0rc5)"},
    },
    "checks_before_commit": V["CHECKS"],
    "not_done": [
        "any live run of 1.10.0rc3: the stages S6 and S6b are proposed, not approved; S7 and full collection deferred "
        "(evidence/1.10.0/budget/NEXT_STAGES.json)",
        "the client's VM checks (the VM is deallocated; no restart, SSH connection, key installation or Azure test "
        "was part of this task)",
        "the full category scope (the exact queue: evidence/1.9.0/live/INCOMPLETE_QUEUE_190.csv); an above-window "
        "partition union",
        "schedules (off), Classic (disabled, not approved), support and IP terms",
    ],
    "earlier_publication_1.9.0rc4": pub_old,
}
write("manifests/PUBLICATION.json", json.dumps(pub_new, indent=1, ensure_ascii=False) + "\n")

# --- 6. nothing else changed; no placeholder left; then the file map and the checksums --------------------------
changed = {p.relative_to(REPO).as_posix() for p in WRITTEN}
for f, digest in old_blobs.items():
    p = REPO / f
    if f.startswith("source/") or f in changed or f in ("manifests/SHA256SUMS.txt", "manifests/FILE_MAP.csv"):
        continue
    assert p.is_file() and sha(p.read_bytes()) == digest, f"{f} changed without being listed"
left = []
scan = set(WRITTEN) | set(ev.rglob("*")) | set((REPO / "review").rglob("*")) | set((REPO / "manifests").rglob("*"))
for p in sorted(scan - VERBATIM):
    if p.is_file() and re.search(rb"@@[A-Z0-9_]+@@", p.read_bytes()):
        left.append(p.relative_to(REPO).as_posix())
assert not left, left
print("placeholders: none left outside the", len(VERBATIM), "scripts copied byte for byte")

git("add", "-A")
git("add", "-f", "source")
assert git("write-tree", "--prefix=source/") == REL_TREE
tracked = set(git("ls-files").splitlines())
on_disk = {p.relative_to(REPO).as_posix() for p in ev.rglob("*") if p.is_file()}
assert on_disk <= tracked, sorted(on_disk - tracked)[:5]
files = sorted(tracked - {"manifests/SHA256SUMS.txt", "manifests/FILE_MAP.csv"})
old_map = {r["path"]: r for r in csv.DictReader(io.StringIO(read("manifests/FILE_MAP.csv")))}
ev_files = {f["published"]: f for f in json.loads((build / "FILES.json").read_text("utf-8"))}
tr_pub = {t["published"]: t for t in transforms}
buf = io.StringIO()
w = csv.writer(buf, lineterminator="\n")
w.writerow(["path", "sha256", "bytes", "origin", "original_sha256", "state"])
for f in files + ["manifests/SHA256SUMS.txt"]:
    if f == "manifests/SHA256SUMS.txt":
        w.writerow([f, "", "", "generated for this publication (lists every other file)", "", "regenerated for 1.10"])
        continue
    b = (REPO / f).read_bytes()
    if f.startswith("source/"):
        row = [f, sha(b), len(b), f"collector 1.10.0rc3: {REL[:7]}:{SRC}/{f[7:]}", sha(b), "unchanged (development tree)"]
    elif f in tr_pub:
        t = tr_pub[f]
        row = [f, sha(b), len(b), t["original"].replace("private:C:/m8/", "task-1.10:"), t["original_sha256"],
               "redacted (REDACTIONS.csv)"]  # fmt: skip
    elif f in ev_files and REPO / f not in WRITTEN:
        o = ev_files[f]["origin"].replace("private:C:/m8/", "task-1.10:")
        row = [f, sha(b), len(b), o, sha(b) if o.startswith("task-1.10:") else "", "added for 1.10"]
    elif f in changed and f in old_map:
        row = [f, sha(b), len(b), old_map[f]["origin"], old_map[f]["original_sha256"],
               "updated for 1.10 (DOC_CORRECTIONS.md)"]  # fmt: skip
    elif f in changed or f not in old_map:
        row = [f, sha(b), len(b), "added for 1.10", "", "added for 1.10"]
    elif f in LE_BY_PATH:
        o, le = old_map[f], LE_BY_PATH[f]
        assert o["sha256"] == sha(b) == le["published_sha256"] and o["original_sha256"] == le["file_map_1.9_original_sha256"]
        row = [f, o["sha256"], o["bytes"], o["origin"], le["original_sha256"],
               "line ends written as LF in 1.9; the original's hash given in 1.10 (REDACTIONS.csv, DOC_CORRECTIONS.md)"]
    else:
        o = old_map[f]
        assert o["sha256"] == sha(b), f"{f} changed without being listed"
        row = [f, o["sha256"], o["bytes"], o["origin"], o["original_sha256"], o["state"]]
    w.writerow(row)
(REPO / "manifests" / "FILE_MAP.csv").write_bytes(buf.getvalue().encode("utf-8"))
even_csv("manifests/FILE_MAP.csv")
git("add", "manifests/FILE_MAP.csv")
lines = []
for f in sorted(set(git("ls-files").splitlines()) - {"manifests/SHA256SUMS.txt"}):
    lines.append(f"{sha((REPO / f).read_bytes())}  {f}")
(REPO / "manifests" / "SHA256SUMS.txt").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
git("add", "manifests/SHA256SUMS.txt")
now = set(git("ls-files").splitlines())
removed, added = sorted(old_files - now), sorted(now - old_files)
print("staged:", len(now), "files;", len(added), "added;", len(removed), "removed (all under source/):",
      all(r.startswith("source/") for r in removed), removed)  # fmt: skip
