"""PRIVATE (workstation): copies a private evidence folder to a publishable one, replacing private identifiers.

    python -I sanitize.py SRC DST PATTERNS_TSV

- Text files (valid UTF-8, no NUL byte): every literal of PATTERNS_TSV (label TAB literal) is replaced, longest
  first and in any ASCII case (as scan6.py finds them), by ``[redacted:<label>]`` (a key fingerprint by its masked
  form ``…4aef98`` or ``…022e50``).
- Gzip files: decompressed and scanned (any ASCII case); one holding a pattern is REFUSED (a stored page is never
  edited).
- Other binary files are copied when they hold no pattern; any file that is neither UTF-8 text nor a known
  binary type is REFUSED (never skipped).
- Writes DST/FILE_MAP.csv (path, original SHA-256, published SHA-256, changed, labels, commitment) for every file.
  A changed file's original SHA-256 is withheld: the masked identifiers are short and guessable (a host or user
  name, a folder), and a published hash of the unmasked file would let a guess be confirmed offline. In its place,
  original_commitment is HMAC-SHA256 of the unmasked file under a private 32-byte key ([redacted:workstation-path]/priv/
  original_commitment.key, never published): given the key and the private original on request, anyone can check
  that the original is the one this publication committed to; without the key the commitment confirms nothing.
Exit 0 only when nothing was refused.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import hmac
import re
import shutil
import sys
from pathlib import Path

SRC, DST, PATS = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
KEY = Path("[redacted:workstation-path]/priv/original_commitment.key").read_bytes()  # private; refuses to run without it
assert len(KEY) == 32, "the commitment key must be 32 bytes"
BINARY = {".gz", ".png", ".jpg", ".jpeg", ".webm", ".mp4", ".pdf", ".tgz", ".zip", ".sqlite3", ".dump"}
pats = []
for line in PATS.read_text(encoding="utf-8").splitlines():
    if line.strip():
        label, lit = line.split("\t", 1)
        pats.append((label, lit))
pats.sort(key=lambda x: -len(x[1]))


def repl(label: str) -> str:
    return {"key-fingerprint-full": "…4aef98", "new-key-fingerprint": "…022e50"}.get(label, f"[redacted:{label}]")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


if DST.exists():
    print(f"REFUSED: {DST} exists")
    sys.exit(2)
rows, refused = [], []
for f in sorted(p for p in SRC.rglob("*") if p.is_file()):
    rel = f.relative_to(SRC).as_posix()
    raw = f.read_bytes()
    out = DST / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    labels: dict[str, int] = {}
    if f.suffix.lower() in BINARY:
        body = raw
        if f.suffix.lower() == ".gz":
            try:
                body = gzip.decompress(raw)
            except OSError as e:
                refused.append((rel, f"gzip unreadable: {e}"))
                continue
        folded = body.lower()  # bytes.lower() folds ASCII only, as scan6.py does
        hits = [lab for lab, lit in pats if lit.encode("utf-8").lower() in folded]
        if hits:
            refused.append((rel, "binary holds: " + ",".join(sorted(set(hits)))))
            continue
        shutil.copyfile(f, out)
        rows.append((rel, sha(raw), sha(raw), "no", "", ""))
        continue
    if b"\x00" in raw:
        refused.append((rel, "NUL byte in a file not typed as binary"))
        continue
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        refused.append((rel, f"not UTF-8: {e}"))
        continue
    for lab, lit in pats:  # any ASCII case of the literal (scan6.py folds ASCII case too)
        mask = repl(lab)
        text, n = re.compile(re.escape(lit), re.IGNORECASE | re.ASCII).subn(lambda _m: mask, text)
        if n:
            labels[lab] = labels.get(lab, 0) + n
    new = text.encode("utf-8")
    out.write_bytes(new)
    if new != raw:
        rows.append((rel, "withheld", sha(new), "yes", ";".join(f"{k}={v}" for k, v in sorted(labels.items())),
                     "hmac-sha256:" + hmac.new(KEY, raw, hashlib.sha256).hexdigest()))
    else:
        rows.append((rel, sha(raw), sha(new), "no", "", ""))
with (DST / "FILE_MAP.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(["path", "sha256_original", "sha256_published", "changed", "redactions", "original_commitment"])
    w.writerows(rows)
print(f"files {len(rows)}, changed {sum(1 for r in rows if r[3] == 'yes')}, refused {len(refused)}")
for r in refused:
    print("REFUSED:", r[0], "-", r[1])
sys.exit(1 if refused else 0)
