"""Checks the spending ledger's hash chain from its published event log (EVENTS.csv), offline, standard library only.

    python3 -I verify_ledger_chain.py EVENTS.csv [REDACTIONS.csv]

Each event's hash is SHA-256 of "prev_hash|at|kind|ref|detail" (detail: the JSON text exactly as stored), and each
event's prev_hash is the hash of the event before it (the first one's is 64 zeros or as recorded). Every event is
checked for its link to the one before. Its own hash is recomputed too, except where the published copy masks a
private identifier inside its detail (an event whose detail holds "[redacted:" or a masked fingerprint "…"): such an
event cannot be recomputed from the published text, and it is counted and listed apart, never passed silently.
Exit 0 when every link holds and every recomputable hash matches, 1 otherwise.
"""

from __future__ import annotations

import csv
import hashlib
import sys

csv.field_size_limit(10**9)


def main() -> int:
    rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8", newline="")))
    prev = None
    linked = recomputed = 0
    masked: list[str] = []
    bad: list[str] = []
    for r in rows:
        if prev is not None:
            if r["prev_hash"] != prev:
                bad.append(f"seq {r['seq']}: prev_hash is not the hash of seq {int(r['seq']) - 1}")
            else:
                linked += 1
        if "[redacted:" in r["detail"] or "…" in r["detail"]:
            masked.append(r["seq"])
        else:
            h = hashlib.sha256(f"{r['prev_hash']}|{r['at']}|{r['kind']}|{r['ref']}|{r['detail']}".encode()).hexdigest()
            if h != r["hash"]:
                bad.append(f"seq {r['seq']}: hash does not match its content")
            else:
                recomputed += 1
        prev = r["hash"]
    print(f"events {len(rows)}: links checked {linked} of {max(len(rows) - 1, 0)}; hashes recomputed and matching "
          f"{recomputed}; not recomputable (a private identifier masked in the published detail) {len(masked)}"
          + (f": seq {', '.join(masked)}" if masked else ""))
    for b in bad:
        print("FAIL " + b)
    print("chain OK" if not bad else f"chain FAILED: {len(bad)} problem(s)")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
