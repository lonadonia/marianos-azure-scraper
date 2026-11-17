"""PRIVATE (workstation): the scan of everything to be published for the private identifiers (redact_patterns_rc6.tsv)
and the Oxylabs credential's secret forms, through scan6.py (files and archive members, ASCII case ignored; never
prints a literal).

    python -I scan_all6.py PATH [PATH ...]

The credential file holds one line, NAME:KEY. NAME is the variable name the collector's own source and tests use (a
public identifier, so it is not a pattern); KEY (44 characters) is the secret. Its forms: the key, the whole line,
and the base64 of each. They are written to a temporary pattern file beside the identifiers' (in the job's private
tmp folder, removed afterwards whatever the result) and never printed. Exit: scan6.py's (0 clean, 1 a hit, 2 an item
that could not be read, never skipped).
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CRED = Path("[redacted:workstation-path]/data/local/oxylabs.env")
IDS = Path("[redacted:workstation-path]/priv/redact_patterns_rc6.tsv")
SCAN = Path("[redacted:workstation-path]/ops6/scan6.py")
TMP = Path("[redacted:workstation-path]")


def main() -> int:
    line = CRED.read_text(encoding="utf-8").strip()
    name, key = line.split(":", 1)
    if not (len(key) == 44 and name.isupper() and ":" not in key):
        print("REFUSED: the credential file is not NAME:KEY as expected")
        return 2
    pats = [("credential-key", key), ("credential-line", line),
            ("credential-key-base64", base64.b64encode(key.encode()).decode()),
            ("credential-line-base64", base64.b64encode(line.encode()).decode())]
    fd, tmp = tempfile.mkstemp(suffix=".tsv", dir=TMP)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(IDS.read_text(encoding="utf-8"))
            fh.write("".join(f"{a}\t{b}\n" for a, b in pats))
        return subprocess.run([sys.executable, "-I", str(SCAN), tmp, *sys.argv[1:]]).returncode
    finally:
        os.remove(tmp)


if __name__ == "__main__":
    raise SystemExit(main())
