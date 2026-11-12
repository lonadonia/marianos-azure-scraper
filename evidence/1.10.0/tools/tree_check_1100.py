"""Checks that a folder holds, file for file, a Git tree: every file of the tree present with the same blob id
(computed from the file's bytes), and nothing else except the folders a local install and test run create.

    python -I tree_check_1100.py <folder> <git repository> <tree-ish> <out.json>

Exit 0 when identical. The record names the tree, each difference, and the generated folders it left aside."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

GENERATED = (".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()  # noqa: S324 (Git's own object id)


def main() -> int:
    folder, repo, treeish, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
    tree = subprocess.run(["git", "-C", repo, "rev-parse", treeish], capture_output=True, text=True,
                          check=True).stdout.strip()  # fmt: skip
    listing = subprocess.run(["git", "-C", repo, "-c", "core.quotepath=off", "ls-tree", "-r", "-z", tree],
                             capture_output=True, check=True).stdout.decode("utf-8")  # fmt: skip
    want: dict[str, str] = {}
    for entry in filter(None, listing.split("\x00")):
        meta, path = entry.split("\t", 1)
        mode, kind, oid = meta.split()
        assert kind == "blob", entry
        want[path] = oid
    missing, different, extra, left_aside = [], [], [], set()
    for path, oid in sorted(want.items()):
        p = folder / path
        if not p.is_file():
            missing.append(path)
        elif blob_id(p.read_bytes()) != oid:
            different.append(path)
    for top, dirs, files in os.walk(folder):
        for d in [d for d in dirs if d in GENERATED]:
            left_aside.add(d)
            dirs.remove(d)  # not walked: what an install and a test run create
        for name in files:
            rel = (Path(top) / name).relative_to(folder).as_posix()
            if rel not in want:
                extra.append(rel)
    extra.sort()
    rec = {
        "folder": str(folder),
        "tree_ish": treeish,
        "tree": tree,
        "files_in_tree": len(want),
        "missing": missing,
        "different": different,
        "extra": extra,
        "generated_folders_left_aside": sorted(left_aside),
        "identical": not (missing or different or extra),
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    out.write_text(json.dumps(rec, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: rec[k] for k in ("tree", "files_in_tree", "identical")}),
          len(missing), "missing,", len(different), "different,", len(extra), "extra")  # fmt: skip
    return 0 if rec["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
