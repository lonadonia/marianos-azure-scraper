"""PRIVATE (workstation): the publishable copy of one stage's evidence folder.

    python -I make_public_stage.py SRC DST PATTERNS_TSV

1. Every file of SRC is copied to a temporary folder except the stored pages (stored/<run>/live/: the listing pages,
   product pages, provider answers and robots files the run captured), which stay private: each is listed in
   STORED_PAGES_PRIVATE.csv with its SHA-256 and size, so a published reference (provenance.json, listing_pages.csv)
   can be matched to the private original on request.
   A file of the run's own staged exports (stored/<run>/exports/) byte-identical to the same file of the
   collector's export command (export/) is published once, under export/ (NOT_REPEATED.csv names each).
2. sanitize.py replaces the private identifiers of PATTERNS_TSV in every text file and refuses anything it cannot
   read (its FILE_MAP.csv records each file's original and published SHA-256).
3. A published file above 8 MB is written gzip-compressed (name + .gz, header time 0) and removed uncompressed;
   COMPRESSED.csv gives each one's uncompressed SHA-256 (the value FILE_MAP.csv and the manifests name).
4. DST/SHA256SUMS lists every published file.
Exit 0 only when sanitize.py refused nothing.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SRC, DST, PATS = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
HERE = Path(__file__).resolve().parent
if DST.exists():
    print(f"REFUSED: {DST} exists")
    sys.exit(2)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


with tempfile.TemporaryDirectory() as tmp:
    stage = Path(tmp) / SRC.name
    private = []
    not_repeated: list[tuple[str, str, str]] = []
    for f in sorted(p for p in SRC.rglob("*") if p.is_file()):
        rel = f.relative_to(SRC)
        parts = rel.parts
        if rel.as_posix() == "SHA256SUMS":
            continue
        if len(parts) >= 4 and parts[0] == "stored" and parts[2] == "live":
            private.append((rel.as_posix(), sha(f), f.stat().st_size))
            continue
        if len(parts) == 4 and parts[0] == "stored" and parts[2] == "exports":
            twin = SRC / "export" / parts[3]
            if twin.is_file() and twin.read_bytes() == f.read_bytes():
                not_repeated.append((rel.as_posix(), f"export/{parts[3]}", sha(f)))
                continue
        out = stage / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, out)
    with (stage / "STORED_PAGES_PRIVATE.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["path_in_the_private_evidence", "sha256", "bytes", "published"])
        for rel, digest, size in private:
            w.writerow([rel, digest, size, "no: a stored page stays private; its SHA-256 identifies it"])
    with (stage / "NOT_REPEATED.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["path_in_the_private_evidence", "published_as", "sha256"])
        w.writerows(not_repeated)
    r = subprocess.run([sys.executable, "-I", str(HERE / "sanitize6.py"), str(stage), str(DST), str(PATS)])
    if r.returncode != 0:
        print("REFUSED by sanitize6.py")
        sys.exit(1)
compressed = []
for p in sorted(q for q in DST.rglob("*") if q.is_file()):
    if p.stat().st_size > 8 * 1024 * 1024 and p.suffix != ".gz":
        raw = p.read_bytes()
        gz = p.with_name(p.name + ".gz")
        gz.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
        assert gzip.decompress(gz.read_bytes()) == raw
        compressed.append((p.relative_to(DST).as_posix(), gz.relative_to(DST).as_posix(), hashlib.sha256(raw).hexdigest(),
                           len(raw)))
        p.unlink()
with (DST / "COMPRESSED.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(["file", "published_as", "sha256_uncompressed", "bytes_uncompressed"])
    w.writerows(compressed)
lines = []
for p in sorted(q for q in DST.rglob("*") if q.is_file()):
    lines.append(f"{sha(p)}  {p.relative_to(DST).as_posix()}")
(DST / "SHA256SUMS").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))  # LF on every platform
print(f"published copy: {len(lines)} files; stored pages kept private: {len(private)}; not repeated: "
      f"{len(not_repeated)}; compressed: {len(compressed)}")
