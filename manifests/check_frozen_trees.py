"""Checks the three source trees of this repository, file for file, against their checksum lists in manifests/original/:

- source/               collector 1.9.0rc4 (MARIANOS_SOURCE_1.9.0rc4.SHA256SUMS.txt);
- classic-probe-1.7.3/  the shared Classic probe 1.7.3 (CLASSIC_PROBE_1.7.3.SHA256SUMS.txt);
- classic-probe/        the frozen probe 1.6.0, against the 1.8.0rc5 source archive's own list
                        (MARIANOS_SOURCE_1.8.0rc5.SHA256SUMS.txt, its classic_probe/ entries).

In a Git checkout it also compares the Git tree ids of source/ and classic-probe-1.7.3/ with those of their development
commits (manifests/PUBLICATION.json). Standard library only, offline. Run from the repository root:

    python3 manifests/check_frozen_trees.py

Exit 0 when every listed file is present with its SHA-256, no other file is in a tree (except classic-probe/
CLASSIC_PROBE.md, the one note added beside the frozen probe), and, where Git is available, both tree ids match.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIG = ROOT / "manifests" / "original"
LISTS = [
    ("source/", ORIG / "MARIANOS_SOURCE_1.9.0rc4.SHA256SUMS.txt", "source/"),
    ("classic-probe-1.7.3/", ORIG / "CLASSIC_PROBE_1.7.3.SHA256SUMS.txt", "classic-probe-1.7.3/"),
    ("classic-probe/", ORIG / "MARIANOS_SOURCE_1.8.0rc5.SHA256SUMS.txt", "classic_probe/"),
]
ADDED = {"classic-probe/CLASSIC_PROBE.md"}
TREES = {
    "source": "7a4dfa05e526bddefdfeab9777b9616890e129ea",
    "classic-probe-1.7.3": "912801d038092bc84906f6e0c5507388980fb9d8",
}


def expected_files(folder: str, sums: Path, prefix: str) -> dict[str, str]:
    out = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        name = name.lstrip("*")
        if name.startswith(prefix):
            out[folder + name[len(prefix):]] = digest
    return out


def main() -> int:
    failures = 0
    for folder, sums, prefix in LISTS:
        expected = expected_files(folder, sums, prefix)
        bad = []
        for rel, digest in sorted(expected.items()):
            p = ROOT / rel
            if not p.is_file():
                bad.append(f"missing  {rel}")
            elif hashlib.sha256(p.read_bytes()).hexdigest() != digest:
                bad.append(f"differs  {rel}")
        for p in sorted((ROOT / folder).rglob("*")):
            rel = p.relative_to(ROOT).as_posix()
            if p.is_file() and rel not in expected and rel not in ADDED and "__pycache__" not in rel:
                bad.append(f"extra    {rel}")
        for line in bad:
            print(line)
        print(f"{folder:22} {len(expected)} files listed ({sums.name}): "
              f"{len(expected) - sum(1 for b in bad if not b.startswith('extra'))} identical, "
              f"{sum(1 for b in bad if not b.startswith('extra'))} missing or different, "
              f"{sum(1 for b in bad if b.startswith('extra'))} extra")
        failures += len(bad)
    try:
        for folder, tree in TREES.items():
            got = subprocess.run(["git", "rev-parse", f"HEAD:{folder}"], cwd=ROOT, capture_output=True, text=True,
                                 check=True).stdout.strip()
            ok = got == tree
            failures += 0 if ok else 1
            print(f"git tree of {folder}: {got} {'= development tree' if ok else '!= development tree ' + tree}")
    except (OSError, subprocess.CalledProcessError):
        print("git tree ids not checked (not a Git checkout, or Git not available)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
