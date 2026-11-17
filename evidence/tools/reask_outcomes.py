"""What became of each request set aside and asked again (C1), by run, kind and hour of the first answer. No network.

    python -I reask_outcomes.py OUT.csv EVIDENCE_DIR [EVIDENCE_DIR ...]

EVIDENCE_DIR is a stage's evidence folder (db_deferred_requests.csv), named after its stage; a request is counted
once by its id across folders (a later slice of a run holds every request of the run so far, in its latest state).
For each run, kind (repeated_page: a page 2 or later answered with an earlier page's products; missing_facets: a
first page above the window naming no child listing and no brand) and hour (UTC) of the first answer: the requests
set aside, recovered at the first re-ask, recovered at the second, exhausted (both re-asks spent without a counted
answer: the listing stays incomplete, and the coverage gate G3 fails), and still waiting when the run stopped.
Prints the table and writes it to OUT.csv.
"""

from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

csv.field_size_limit(10**9)


def main() -> int:
    out, dirs = Path(sys.argv[1]), [Path(a) for a in sys.argv[2:]]
    latest: dict[str, dict[str, str]] = {}
    stages: dict[str, list[str]] = collections.defaultdict(list)
    for d in dirs:
        for r in csv.DictReader((d / "db_deferred_requests.csv").open(encoding="utf-8", newline="")):
            latest[r["id"]] = r  # the later folder's row is the request's later state
            if d.name not in stages[r["run_id"]]:
                stages[r["run_id"]].append(d.name)
    agg: dict[tuple[str, str, str], collections.Counter] = collections.defaultdict(collections.Counter)
    for r in latest.values():
        hour = r["created_at"][:13].replace(" ", "T") + "Z"
        c = agg[("+".join(stages[r["run_id"]]), r["kind"], hour)]
        c["set_aside"] += 1
        if r["state"] == "recovered":
            c[f"recovered_at_reask_{r['reasks_dispatched']}"] += 1
        else:
            c[r["state"]] += 1
    cols = ["set_aside", "recovered_at_reask_1", "recovered_at_reask_2", "exhausted", "waiting"]
    table = []
    for (st, kind, hour), c in sorted(agg.items(), key=lambda x: (x[0][2], x[0][0], x[0][1])):
        other = sum(v for k, v in c.items() if k not in cols)
        table.append({"stages": st, "kind": kind, "hour_utc_of_first_answer": hour, **{k: c[k] for k in cols},
                      "other_states": other})
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(table)
    tot: collections.Counter = collections.Counter()
    for t in table:
        print(f"{t['hour_utc_of_first_answer']}  {t['stages']:<16} {t['kind']:<15} set aside {t['set_aside']:3}  "
              f"recovered 1st {t['recovered_at_reask_1']:3}  2nd {t['recovered_at_reask_2']:3}  "
              f"exhausted {t['exhausted']:3}  waiting {t['waiting']:3}  other {t['other_states']}")
        tot.update({k: t[k] for k in cols})
    print("total", dict(tot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
