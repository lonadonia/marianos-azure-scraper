"""Checks that source/ and classic-probe/ of this repository are, file for file, the source/ and classic_probe/ of
MARIANOS_SOURCE_1.8.0rc5.zip, against that archive's own checksum list (manifests/original/). Standard library
only, offline. Run from the repository root:

    python3 manifests/check_frozen_trees.py

Exit 0 when every listed file is present with its SHA-256 and no other file is in either tree (except
classic-probe/CLASSIC_PROBE.md, the one note added beside the frozen probe).
"""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUMS = ROOT / "manifests/original/MARIANOS_SOURCE_1.8.0rc5.SHA256SUMS.txt"
TREES = {"source/": "source/", "classic_probe/": "classic-probe/"}  # archive folder -> repository folder
ADDED = {"classic-probe/CLASSIC_PROBE.md"}


def main() -> int:
    expected = {}
    not_published = 0
    for line in SUMS.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        name = name.lstrip("*")
        for archive, repo in TREES.items():
            if name.startswith(archive):
                expected[repo + name[len(archive):]] = digest
                break
        else:
            not_published += 1  # release_build/ (build output) and the archive's own index files
    bad = []
    for rel, digest in sorted(expected.items()):
        p = ROOT / rel
        if not p.is_file():
            bad.append(f"missing  {rel}")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            bad.append(f"differs  {rel}")
    extra = []
    for repo in TREES.values():
        for p in sorted((ROOT / repo).rglob("*")):
            rel = p.relative_to(ROOT).as_posix()
            if p.is_file() and rel not in expected and rel not in ADDED and "__pycache__" not in rel:
                extra.append(f"extra    {rel}")
    for line in bad + extra:
        print(line)
    print(f"{len(expected)} files listed for source/ and classic-probe/: {len(expected) - len(bad)} identical, "
          f"{len(bad)} missing or different, {len(extra)} extra; {not_published} archive entries outside these trees "
          f"(release_build/ and the archive index), not published")
    return 1 if bad or extra else 0


if __name__ == "__main__":
    sys.exit(main())
