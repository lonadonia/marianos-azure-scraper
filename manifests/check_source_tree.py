"""Checks source/ file for file against manifests/MARIANOS_SOURCE_1.10.0rc7.SHA256SUMS.txt and, in a Git checkout,
compares the Git tree ID of source/ with that of the collector's development commit (manifests/PUBLICATION.json).
Standard library only, offline. Run from the repository root:

    python3 manifests/check_source_tree.py

Exit 0 when every listed file is present with its SHA-256, no other file is in source/, and, where Git is available,
the tree ID matches e370b31320fdf825749ecc8a5da2c7544137cc25: the development tree fe89f133cf7551b6cb7a26633c445508fe0c66fd of collector 1.10.0rc7 (commit ec10cde09feedf5a5bab04169e6dbadb8592b5ce) with
one change, the test VM's host masked in source/docs/AZURE_VM.md (manifests/REDACTIONS.csv).
"""

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMS = ROOT / "manifests" / "MARIANOS_SOURCE_1.10.0rc7.SHA256SUMS.txt"
TREE = "e370b31320fdf825749ecc8a5da2c7544137cc25"


def main() -> int:
    expected = {}
    for line in SUMS.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        expected[name.lstrip("*")] = digest
    bad = []
    for rel, digest in sorted(expected.items()):
        p = ROOT / rel
        if not p.is_file():
            bad.append(f"missing  {rel}")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            bad.append(f"differs  {rel}")
    for p in sorted((ROOT / "source").rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if p.is_file() and rel not in expected and "__pycache__" not in rel and "/.venv/" not in f"/{rel}":
            bad.append(f"extra    {rel}")
    print(f"source/: {len(expected)} files listed, {len(bad)} problem(s)")
    for b in bad[:50]:
        print("  " + b)
    tree_ok = True
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD:source"], cwd=ROOT, capture_output=True, text=True, check=True)
        tree_ok = r.stdout.strip() == TREE
        print(f"git tree of source/: {r.stdout.strip()} ({'the published tree' if tree_ok else 'NOT ' + TREE})")
    except (OSError, subprocess.CalledProcessError):
        print("git not available here: tree ID not compared")
    return 0 if not bad and tree_ok else 1


if __name__ == "__main__":
    sys.exit(main())
