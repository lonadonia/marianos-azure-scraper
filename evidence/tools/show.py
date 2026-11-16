"""Condensed views for the recorded walkthrough (reads the collector's JSON output or a run's export; prints plain
lines that fit a 132-column terminal). No network, nothing written.

    marianos ... status --run ID | python3 -I show.py status -
    python3 -I show.py coverage EXPORT_DIR          the CSV rows' states (coverage_by_csv_row.csv)
    python3 -I show.py listings EXPORT_DIR [N]      the first N listings of coverage_reconciliation.csv
    python3 -I show.py result -                     the RESULT line of any command: exit code and its first fields
    python3 -I show.py events -                     a collector JSON-lines log: time, level, event, message
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

W = 130


def cut(s: object) -> str:
    t = str(s)
    return t if len(t) <= W else t[: W - 1] + "~"


def lines_in() -> list[dict]:
    out = []
    for raw in sys.stdin:
        raw = raw.strip()
        if raw.startswith("{"):
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
    return out


def show_status() -> None:
    for d in lines_in():
        if d.get("event") != "RESULT":
            continue
        print(cut(f"exit {d.get('exit_code')}  command {d.get('command')}"))
        r = d.get("result") or {}
        run = r.get("run") or {}
        if run:
            keys = ("run_id", "status", "trigger", "dataset", "pilot", "stop_code", "created_at", "finished_at",
                    "outcome", "worker_running")
            for k in keys:
                print(cut(f"  {k:<16} {run.get(k)}"))
            if run.get("stop_detail"):
                print(cut(f"  stop_detail      {run['stop_detail']}"))
            print(cut(f"  records          {json.dumps(run.get('records_by_status'))}"))
        for k in ("runs", "holds", "published", "provider", "ledger", "ceiling"):
            if k in r:
                print(cut(f"  {k:<16} {json.dumps(r[k], default=str)}"))


def show_result() -> None:
    for d in lines_in():
        if d.get("event") == "RESULT" or "exit_code" in d and "event" not in d:
            print(cut(f"exit {d.get('exit_code')}  {json.dumps(d.get('result'), default=str)}"))
        elif d.get("level") in ("WARN", "ERROR"):
            print(cut(f"{d.get('level')} {d.get('event')}: {d.get('message', '')}"))


def show_events() -> None:
    for d in lines_in():
        t = str(d.get("ts", ""))[11:19]
        msg = d.get("message") or {k: v for k, v in d.items() if k not in ("ts", "level", "event", "collector")}
        print(cut(f"{t} {d.get('level', ''):<5} {d.get('event', '')} {msg}"))


def show_coverage(exp: Path) -> None:
    with (exp / "coverage_by_csv_row.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("no rows")
        return
    cols = [c for c in ("csv_row", "category", "listings_planned", "listings_complete", "listings_incomplete",
                        "listings_not_read", "pages_completed", "unique_identities", "status") if c in rows[0]]
    print(cut("  ".join(cols or list(rows[0])[:8])))
    for r in rows:
        print(cut("  ".join(str(r[c]) for c in (cols or list(r)[:8]))))


def show_listings(exp: Path, n: int) -> None:
    with (exp / "coverage_reconciliation.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    cols = [c for c in ("csv_row", "sub_category", "listing_id", "listing_kind", "reported_total", "pages_completed",
                        "unique_identities", "duplicates", "status") if rows and c in rows[0]]
    print(cut("  ".join(cols)))
    for r in rows[:n]:
        print(cut("  ".join(str(r[c]) for c in cols)))
    print(f"({len(rows)} listings in all)")


def main() -> int:
    what = sys.argv[1]
    if what == "status":
        show_status()
    elif what == "result":
        show_result()
    elif what == "events":
        show_events()
    elif what == "coverage":
        show_coverage(Path(sys.argv[2]))
    elif what == "listings":
        show_listings(Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 20)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
