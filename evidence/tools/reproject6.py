"""The full-run projection restated from a live run's measured rates (R6, then R7), after each slice. No network.

    python -I reproject6.py ESTIMATE_JSON LEDGER_STATUS_JSON EVIDENCE_DIR [EVIDENCE_DIR ...]

ESTIMATE_JSON       the offline estimate (ESTIMATE_1.10.0rc6.json: pages of a full run, low and high)
LEDGER_STATUS_JSON  the campaign's ledger status after the latest slice (mstage6 ledger-status)
EVIDENCE_DIR        the run's slice folders in order (stage_evidence6.sh); the last one holds every row of the run

Measured: the run's submissions (every ledger row of its stages: settled, unknown and released alike are counted as the
ledger counts them), its counted listing pages (distinct pages asked whose answer was counted: db_listing_pages rows completed or
re-asked with the verdict new, completed or partial_overlap) and its segments' active seconds. The rest of a full run is the estimate's pages less the pages counted, at the run's own
submissions per counted page. Printed with the envelope's remaining room; nothing is rounded in the run's favour.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

RATE_USD = 0.0015
csv.field_size_limit(10**9)


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))


def main() -> int:
    est = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    led = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    dirs = [Path(a) for a in sys.argv[3:]]
    subs = 0
    for d in dirs:
        with (d / "ledger_reservations.csv").open(encoding="utf-8", newline="") as fh:
            subs += sum(1 for r in csv.DictReader(fh) if r["state"] != "released_unsent")
    last = dirs[-1]
    with (last / "db_listing_pages.csv").open(encoding="utf-8", newline="") as fh:
        pages = [r for r in csv.DictReader(fh)]
    counted = {(r["category_source_id"], r["taxonomy_id"], r["partition_key"], r["route"], r["requested_page"],
                r["requested_filter"]) for r in pages
               if r["state"] in ("completed", "reasked") and r["verdict"] in ("new", "completed", "partial_overlap")}
    with (last / "db_collection_segments.csv").open(encoding="utf-8", newline="") as fh:
        segs = list(csv.DictReader(fh))
    seconds = sum(float(s["active_s"] or 0) for s in segs)
    n = len(counted)
    per_page = subs / n if n else float("nan")
    room_usd = float(led["projects"]["marianos"]["spendable_in_envelope_usd"])
    room_subs = math.floor(room_usd / RATE_USD + 1e-9)
    run_ids = sorted({r["run_id"] for r in pages})
    out = {"run_id": run_ids[0] if len(run_ids) == 1 else run_ids, "slices": [d.name for d in dirs],
           "submissions_so_far": subs, "pages_counted": n,
           "submissions_per_counted_page": round(per_page, 3),
           "seconds_of_execution": round(seconds), "seconds_per_counted_page": round(seconds / n, 2) if n else None,
           "envelope_room_usd": room_usd, "envelope_room_submissions": room_subs, "projection": {}}
    for k in ("low", "high"):
        left = max(est["pages"][k] - n, 0)
        need = math.ceil(left * per_page)
        out["projection"][k] = {"full_run_pages": est["pages"][k], "pages_left": left, "submissions_left": need,
                                "usd_left": round(need * RATE_USD, 4),
                                "shortfall_submissions": max(need - room_subs, 0),
                                "shortfall_usd": round(max(need - room_subs, 0) * RATE_USD, 4),
                                "hours_left_at_run_rate": round(left * seconds / n / 3600, 2) if n else None}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
