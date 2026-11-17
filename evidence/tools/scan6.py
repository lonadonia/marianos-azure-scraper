"""PRIVATE (workstation): literal scan of files and archive members for the private identifiers of PATTERNS_TSV
(label TAB literal), matched without regard to ASCII case. Never prints a literal: label, path, member, count. Gzip, tar (any compression) and zip
members are opened (nested to depth 3). Exit 1 on a hit, 2 on an item that could not be read (never skipped),
0 when clean.

    python -I scan6.py PATTERNS_TSV PATH...
"""
from __future__ import annotations

import gzip
import io
import sys
import tarfile
import zipfile
from pathlib import Path

pats = []
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if line.strip():
        label, lit = line.split("\t", 1)
        pats.append((label, lit.encode("utf-8")))
hits: list[tuple[str, str, str, int]] = []
errors: list[tuple[str, str]] = []
files = 0


def scan(data: bytes, where: str, member: str, depth: int) -> None:
    folded = data.lower()  # ASCII case folded: a path or a host name in upper, lower or mixed case all count
    for label, lit in pats:
        n = folded.count(lit.lower())
        if n:
            hits.append((label, where, member, n))
    if depth >= 3:
        return
    name = member or where
    low = name.lower()
    try:
        if low.endswith((".tar.gz", ".tgz", ".tar", ".tar.xz", ".tar.bz2")):
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                for m in t.getmembers():
                    if m.isfile():
                        f = t.extractfile(m)
                        if f is not None:
                            scan(f.read(), where, f"{member}!{m.name}" if member else m.name, depth + 1)
        elif low.endswith(".gz"):
            scan(gzip.decompress(data), where, (member + "!" if member else "") + "<gunzip>", depth + 1)
        elif low.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for n in z.namelist():
                    scan(z.read(n), where, f"{member}!{n}" if member else n, depth + 1)
    except Exception as e:  # an archive that cannot be opened is reported, never skipped
        errors.append((f"{where}:{member}", repr(e)[:200]))


for root in sys.argv[2:]:
    p = Path(root)
    if not p.exists():  # a path named but absent is reported, never skipped
        errors.append((root, "no such file or folder"))
        continue
    for f in ([p] if p.is_file() else sorted(x for x in p.rglob("*") if x.is_file() and ".git" not in x.parts)):
        files += 1
        try:
            scan(f.read_bytes(), f.as_posix(), "", 0)
        except OSError as e:
            errors.append((f.as_posix(), repr(e)[:200]))
for label, where, member, n in hits:
    print(f"HIT {label} {where} {member} x{n}")
for where, e in errors:
    print(f"UNREADABLE {where} {e}")
print(f"scanned {files} files: {len(hits)} hits, {len(errors)} unreadable")
sys.exit(1 if hits else 2 if errors else 0)
