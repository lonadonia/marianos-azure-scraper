"""PRIVATE (workstation): compares two outputs of pub_state.sh (the published state of one target) section by
section, no network. Prints one line per section, EQUAL or DIFFERENT, with the differing lines; for latest.json it
also compares the fields that name the dataset (publication_id, run_id, manifest_key, manifest_sha256, mode) apart
from those rewritten on every publication or rollback (version, written_at).

    python -I pub_compare.py BEFORE.txt AFTER.txt [--expect-equal SECTION ...] [--expect-different SECTION ...]

Exit 0 when every section named after --expect-equal is EQUAL (all sections when neither option names one) and every
section named after --expect-different is DIFFERENT (a publication that replaces another), else 1. The output is
UTF-8 with LF line ends on every system.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATASET_FIELDS = ("publication_id", "run_id", "manifest_key", "manifest_sha256", "mode")


def sections(path: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    cur = "(head)"
    for line in Path(path).read_bytes().decode("utf-8").splitlines():
        if line.startswith("== "):
            cur = line[3:].split(" (")[0].strip()
            if cur.startswith("exports of the published run"):
                cur = "exports of the published run"
            out[cur] = []
        else:
            out.setdefault(cur, []).append(line)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[union-attr]
    args = sys.argv[1:]
    a, b = args[0], args[1]
    named: dict[str, list[str]] = {"--expect-equal": [], "--expect-different": []}
    cur = None
    for x in args[2:]:
        if x in named:
            cur = x
        elif cur is None:
            raise SystemExit(f"unexpected argument {x!r}")
        else:
            named[cur].append(x)
    expect, differ = named["--expect-equal"], named["--expect-different"]
    print(f"expected: equal {expect or ('every section' if not differ else 'none named')}; "
          f"different {differ or 'none named'}")
    sa, sb = sections(a), sections(b)
    ok = True
    for name in sorted(set(sa) | set(sb)):
        la, lb = sa.get(name), sb.get(name)
        same = la == lb
        print(f"{'EQUAL    ' if same else 'DIFFERENT'} {name}")
        if not same:
            for x in sorted(set(la or []) - set(lb or [])):
                print(f"    only before: {x[:200]}")
            for x in sorted(set(lb or []) - set(la or [])):
                print(f"    only after:  {x[:200]}")
        if ((name in expect) or (not expect and not differ)) and not same:
            ok = False
        if name in differ and same:
            ok = False
    if "latest.json" in sa and "latest.json" in sb:
        ja = json.loads("\n".join(sa["latest.json"]).strip() or "{}")
        jb = json.loads("\n".join(sb["latest.json"]).strip() or "{}")
        fa = {k: ja.get(k) for k in DATASET_FIELDS}
        fb = {k: jb.get(k) for k in DATASET_FIELDS}
        print(f"{'EQUAL    ' if fa == fb else 'DIFFERENT'} latest.json dataset fields {list(DATASET_FIELDS)}")
        print(f"    version {ja.get('version')} -> {jb.get('version')}; written_at {ja.get('written_at')} -> "
              f"{jb.get('written_at')}")
        if "latest.json dataset fields" in expect and fa != fb:
            ok = False
        if "latest.json dataset fields" in differ and fa == fb:
            ok = False
    print("RESULT", "as expected" if ok else "NOT as expected")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
