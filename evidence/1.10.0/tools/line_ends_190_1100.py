"""The files of evidence/1.9.0 whose line ends 1.9 converted without a record. 1.9's builder wrote every text file
with LF; where the private original had Windows line ends (CRLF), that change was neither in REDACTIONS.csv nor in
FILE_MAP.csv, which gave the published file's SHA-256 as the original's. This script finds those files by reading
each private original named by FILE_MAP.csv (origin "task-1.9:<path under C:/m8>"), and checks for each that the
original, with every CRLF written as LF, is byte for byte the published file. Where a run's own exports/manifest.json
(written by the collector) names the file, it also checks that the manifest's hash is the original's. It reads the
1.8 rows too: each archive file must match the original hash FILE_MAP.csv gives. Nothing is changed here; the
result goes to OUT_JSON for publish_1100.py.

Usage: python -I line_ends_190_1100.py REPO OUT_JSON"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

REPO, OUT = Path(sys.argv[1]), Path(sys.argv[2])
PRIVATE = Path("C:/m8")
ARCHIVE_18 = Path("C:/m7/in/ev/MARIANOS_EVIDENCE_1.8.0rc5")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


fm = list(csv.DictReader(io.StringIO((REPO / "manifests" / "FILE_MAP.csv").read_bytes().decode("utf-8"))))
red = {r["published"] for r in csv.DictReader(io.StringIO((REPO / "manifests" / "REDACTIONS.csv").read_bytes().decode("utf-8")))}
files, excerpts, kinds = [], [], Counter()
matched = 0
for r in fm:
    o = r["origin"]
    if not o.startswith("task-1.9:"):
        continue
    rel = o[len("task-1.9:"):]
    if " (" in rel:  # an excerpt: lines or a record taken from a larger file, named in the origin
        excerpts.append(r["path"])
        continue
    raw = (PRIVATE / rel).read_bytes()
    if sha(raw) == r["original_sha256"]:
        matched += 1
        continue
    pub = (REPO / r["path"]).read_bytes()
    assert sha(pub) == r["sha256"], r["path"]
    crlf = raw.count(b"\r\n")
    assert crlf and raw.replace(b"\r\n", b"\n") == pub, f"{r['path']}: differs by more than its line ends"
    assert r["path"] not in red, r["path"]
    bare_lf = raw.count(b"\n") - crlf
    item = {
        "published": r["path"],
        "origin": o,
        "original_sha256": sha(raw),
        "original_bytes": len(raw),
        "published_sha256": r["sha256"],
        "crlf": crlf,
        "bare_lf_in_original": bare_lf,
        "lf_written_back_as_crlf_gives_the_original": pub.replace(b"\n", b"\r\n") == raw,
        "file_map_1.9_original_sha256": r["original_sha256"],
        "file_map_1.9_state": r["state"],
    }
    parts = Path(r["path"]).parts
    if "exports" in parts:
        manifest = REPO / Path(*parts[: parts.index("exports") + 1]) / "manifest.json"
        if manifest.is_file():
            named = json.loads(manifest.read_bytes().decode("utf-8")).get("files", {}).get(parts[-1])
            if named:
                assert named["sha256"] == item["original_sha256"] and named["size"] == len(raw), r["path"]
                item["run_manifest_names_the_original"] = True
    files.append(item)
    kinds[Path(r["path"]).suffix] += 1

archive_ok = archive_rows = 0
for r in fm:
    if r["origin"].startswith("evidence-archive:"):
        archive_rows += 1
        p = ARCHIVE_18 / r["origin"][len("evidence-archive:"):]
        assert p.is_file() and sha(p.read_bytes()) == r["original_sha256"], r["path"]
        archive_ok += 1

summary = {
    "task_1.9_whole_file_rows": matched + len(files),
    "their_original_hash_correct_in_1.9": matched,
    "line_ends_converted_without_a_record": len(files),
    "of_which_lf_back_to_crlf_exact": sum(1 for f in files if f["lf_written_back_as_crlf_gives_the_original"]),
    "of_which_named_by_their_run_manifest": sum(1 for f in files if f.get("run_manifest_names_the_original")),
    "by_extension": dict(sorted(kinds.items())),
    "excerpts_1.9": len(excerpts),
    "rows_1.8_archive_checked": archive_rows,
    "rows_1.8_archive_matching": archive_ok,
}
OUT.write_text(json.dumps({"summary": summary, "files": files, "excerpts": excerpts}, indent=1) + "\n", "utf-8")
print(json.dumps(summary))
