"""The before/after table of one test file run on two revisions, from the two runs' own JUnit result files.

    python -I cases_table_1100.py <before.junit.xml> <after.junit.xml> <before label> <after label> <out.csv>

One line per test: what it is (a control that must pass on both revisions, or a case of the new behaviour that
must fail before and pass after), the kind of evidence it rests on, its outcome on each revision, the first line
of its failure before, and whether that is what was expected. Nothing is taken from an exit code: each outcome
is the test's own result element. Exits 1 when a line is not as expected or the two runs do not hold the same
tests."""

from __future__ import annotations

import csv
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# The cases of the brief of 2026-11-11, by words of the test names.
CASES = (
    (1, "a repeat that persists through both re-asks", ("keeps_repeating", "asked_again_twice")),
    (2, "a re-ask returns a genuine next page", ("brings_the_next_page", "partial_overlap", "batteries")),
    (3, "a listing above the window lacks its filters", ("above_the_window", "without_filters", "filters_",
                                                         "reask_for_filters", "frozen")),  # fmt: skip
    (4, "lanes, interruption and resume, budget, deadline", ("other_listings", "two_lanes", "provider_fails",
                                                             "worker_killed", "spending_ceiling",
                                                             "daily_window")),  # fmt: skip
    (5, "ordinary pages and carried records", ("ordinary_pages", "carried_from")),
)


def outcomes(path: Path) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for case in ET.parse(path).getroot().iter("testcase"):
        name = str(case.get("name"))
        bad = case.find("failure") if case.find("failure") is not None else case.find("error")
        if bad is not None:
            text = (bad.get("message") or bad.text or "").strip().splitlines()
            out[name] = ("failed" if bad.tag == "failure" else "error", (text[0] if text else "")[:400])
        elif case.find("skipped") is not None:
            out[name] = ("skipped", str(case.find("skipped").get("message") or "")[:400])  # type: ignore[union-attr]
        else:
            out[name] = ("passed", "")
    return out


def main() -> int:
    before, after = outcomes(Path(sys.argv[1])), outcomes(Path(sys.argv[2]))
    label_b, label_a, dest = sys.argv[3], sys.argv[4], Path(sys.argv[5])
    same = set(before) == set(after)
    rows, wrong = [], 0
    for name in sorted(set(before) | set(after), key=lambda n: (case_of(n)[0], n)):
        control = name.startswith("test_control_")
        b, a = before.get(name, ("absent", "")), after.get(name, ("absent", ""))
        expected = ("passed", "passed") if control else ("failed", "passed")
        ok = (b[0], a[0]) == expected
        wrong += 0 if ok else 1
        number, title = case_of(name)
        rows.append(
            {
                "case": number,
                "case_title": title,
                "test": name,
                "kind": "control (must pass on both)" if control else "new behaviour (fails before, passes after)",
                "evidence_type": "OFFLINE REPLAY of saved answers" if "replay" in name else "SYNTHETIC pages",
                f"outcome_{label_b}": b[0],
                f"outcome_{label_a}": a[0],
                f"first_failure_line_{label_b}": b[1],
                "as_expected": "yes" if ok else "NO",
            }
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    controls = sum(1 for r in rows if r["kind"].startswith("control"))
    print(f"{len(rows)} tests: {controls} controls, {len(rows) - controls} new-behaviour cases; "
          f"not as expected: {wrong}; same tests in both runs: {same}")  # fmt: skip
    return 0 if same and not wrong else 1


def case_of(name: str) -> tuple[int, str]:
    for number, title, words in CASES:
        if any(re.search(w, name) for w in words):
            return number, title
    return 0, "the publication result (kept apart from C1)"


if __name__ == "__main__":
    raise SystemExit(main())
