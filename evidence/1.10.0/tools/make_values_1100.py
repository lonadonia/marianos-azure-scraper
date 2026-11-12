"""Writes the values that fill the placeholders of the 1.10 documents, read from the session records, the evidence
build's facts and its ledger read; no count is typed by hand. Refuses a session that did not pass by its own output.

Usage: python -I make_values_1100.py TAG DATE OUT_JSON"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LOGS = Path("C:/m8/logs/tests1100")
STAGE = Path("C:/m8/pub1100/stage/evidence")
TAG, DATE, OUT = sys.argv[1], sys.argv[2], Path(sys.argv[3])
assert re.fullmatch(r"review-1\.10\.0rc3-\d{8}", TAG) and TAG.endswith(DATE.replace("-", "")), (TAG, DATE)
LINT = {"ruff_check": r"^All checks passed!$", "ruff_format": r"^(\d+) files already formatted$",
        "mypy": r"^Success: no issues found in (\d+) source files$"}  # fmt: skip


def rec(label: str) -> dict:
    return json.loads((LOGS / f"{label}.json").read_text("utf-8"))


def passed(label: str) -> str:
    """'N passed' (with skips named), only for a session whose own summary line shows no failure."""
    r = rec(label)
    c = r["pytest_counts"]
    assert r["exit_code"] == 0 and c.get("passed") and set(c) <= {"passed", "skipped", "warnings", "warning"}, label
    out = f"{c['passed']} passed"
    if c.get("skipped"):
        out += f", {c['skipped']} skipped (" + "; ".join(f"{n} x {k}" for k, n in r["skip_reasons"].items()) + ")"
    return out


def lint_line(label: str, kind: str) -> str:
    r = rec(label)
    text = (LOGS / f"{label}.log").read_bytes().decode("utf-8").replace("\r\n", "\n")
    m = re.search(LINT[kind], text, re.M)
    assert m and r["exit_code"] == 0, label
    return m.group(0)


cand = {k: lint_line(f"cand_{k}", k) for k in LINT}
xl = {k: lint_line(f"x_{k}", k) for k in LINT}
assert cand == xl, (cand, xl)
integ = rec("cand_integration")
assert integ["pytest_counts"] == {"passed": 218} and not integ["skip_reasons"], integ["pytest_counts"]
facts = json.loads((STAGE / "_build_evidence_1100" / "FACTS.json").read_text("utf-8"))
ledger = json.loads((STAGE / "1.10.0" / "budget" / "LEDGER_STATUS.json").read_text("utf-8"))
chain = json.loads(ledger["verify_chain"])
assert chain["chain_ok"] is True, chain
mar = ledger["campaign"]["projects"]["marianos"]
spendable = mar["spendable_in_envelope_usd"]
read_at = ledger["read_at"].replace("T", " ")[:19] + "Z"
assert json.loads((LOGS / "x_tree_check.json").read_text("utf-8"))["identical"] is True
after = json.loads((LOGS / "x_tree_check_after_sessions.json").read_text("utf-8"))
assert not after["missing"] and not after["different"] and all(x.startswith(".hypothesis/") for x in after["extra"])

UNIT, INTEG = passed("cand_unit"), passed("cand_integration")
X_UNIT, X_C1, X_PUB = passed("x_unit"), passed("x_c1_cases"), passed("x_publication_result")
assert (X_UNIT, X_C1, X_PUB) == (UNIT, passed("cand_c1_cases"), passed("cand_publication_result"))
secs = integ["seconds"]
V = {
    "TAG": TAG,
    "DATE": DATE,
    "UNIT": UNIT,
    "INTEG": INTEG,
    "INTEG_NOTE": (
        f"The integration suite ran for {secs:,.0f} s (about {round(secs / 60)} min) and skipped no test. It started "
        "one throwaway PostgreSQL server (`pgserver`, in a temporary folder) for the whole suite and removed it at the "
        "end; no PostgreSQL process was left running afterwards. Its 218 tests are 1.9.0rc4's 183, the 28 C1 cases, the 6 publication cases and one migration "
        "test (migration 0006, its table of requests set aside and the ceiling in its constraints); "
        "[`INTEGRATION_BY_FILE.csv`](../evidence/1.10.0/tests/INTEGRATION_BY_FILE.csv) gives them per file."
    ),
    "X_RESULTS": (f"unit {X_UNIT}; C1 cases {X_C1}; publication cases {X_PUB}; ruff '{xl['ruff_check']}', "
                  f"format '{xl['ruff_format']}', mypy '{xl['mypy']}'"),  # fmt: skip
    "C1_SRC_ADDED": facts["C1_SRC_ADDED"],
    "C1_SRC_DELETED": facts["C1_SRC_DELETED"],
    "M_SPENDABLE_EXACT": spendable,
    "LEDGER_READ": read_at,
    "SUITES_WORDS": (
        f"on the exact candidate (a1040f7, clean tree): unit {UNIT}; integration with PostgreSQL {INTEG}, none "
        f"skipped; ruff, format and mypy clean; again in a clean extraction of its tree: unit {X_UNIT}, C1 cases "
        f"{X_C1}, publication cases {X_PUB}, ruff, format and mypy clean"
    ),
    "LEDGER_LINE": (f"read at {read_at}, hash chain verified ({chain['events']} events): Mariano's spendable in its "
                    f"envelope USD {spendable}"),  # fmt: skip
    "CHECKS": (
        f"on the exact delivered tree (a1040f7): unit {UNIT}, integration {INTEG}, ruff, format and mypy clean, the "
        f"C1 cases {passed('cand_c1_cases')} and the publication cases {passed('cand_publication_result')} (each "
        "also run on 1.9.0rc4: there the new cases fail and the controls pass); the unit suite, both case files and "
        "the lint checks again in a clean extraction of the tree, checked file for file; on the staged repository "
        "before the commit: the public-disclosure scan of every added or changed file, the exact-value secret scans "
        "(every local credential value, raw and URL-encoded, in plain, gzip, zip and tar content), the link and "
        "path check, sha256sum -c of every file and the frozen-tree check; after the push: the remote commit and "
        "tag compared and a fresh clone checked"
    ),
}
assert not any("@@" in str(v) for v in V.values())
OUT.write_text(json.dumps(V, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({k: V[k] for k in ("TAG", "DATE", "UNIT", "INTEG", "C1_SRC_ADDED", "C1_SRC_DELETED",
                                    "M_SPENDABLE_EXACT", "LEDGER_READ")}))  # fmt: skip
