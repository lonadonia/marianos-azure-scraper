"""PRIVATE (workstation): Q5's measures of stage evidence folders (stage_evidence.sh), no network.

    python -I q5_compare.py OUT.json EVIDENCE_DIR [EVIDENCE_DIR ...]

Per run: submissions (ledger rows of the stage) by state, results and USD settled, unknown outcomes held, wall time
(run start to end), the time at least one request was in flight (union of each reservation's dispatch-to-settlement
interval) and the time none was, the highest number in flight at once, pages answered and counted, requests set
aside, re-asks and the wait from each request's previous answer to its re-ask, records by status. Only what the
rows state; nothing estimated.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

csv.field_size_limit(1 << 30)


def ts(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None


def rows(ev: Path, name: str) -> list[dict[str, str]]:
    p = ev / name
    return list(csv.DictReader(p.open(encoding="utf-8", newline=""))) if p.exists() else []


def measure(ev: Path) -> dict[str, object]:
    stage = json.loads((ev / "stage_record.json").read_text(encoding="utf-8"))
    run = rows(ev, "db_runs.csv")[0]
    led = rows(ev, "ledger_reservations.csv")
    pages = rows(ev, "db_listing_pages.csv")
    deferred = rows(ev, "db_deferred_requests.csv")
    start, end = ts(run["started_at"]), ts(run["finished_at"])
    wall = (end - start).total_seconds() if start and end else None
    spans = []
    for r in led:
        a, b = ts(r["dispatched_at"]), ts(r["updated_at"])
        if a and b and r["state"] in ("settled", "unknown"):
            spans.append((a, b))
    spans.sort()
    union, cur_a, cur_b = 0.0, None, None
    for a, b in spans:
        if cur_b is None or a > cur_b:
            if cur_b is not None:
                union += (cur_b - cur_a).total_seconds()
            cur_a, cur_b = a, b
        else:
            cur_b = max(cur_b, b)
    if cur_b is not None:
        union += (cur_b - cur_a).total_seconds()
    edges = sorted([(a, 1) for a, _ in spans] + [(b, -1) for _, b in spans], key=lambda e: (e[0], e[1]))
    inflight = peak = 0
    for _, d in edges:
        inflight += d
        peak = max(peak, inflight)
    states: dict[str, int] = {}
    for r in led:
        states[r["state"]] = states.get(r["state"], 0) + 1
    waits = []
    reasks = 0
    for d in deferred:
        atts = json.loads(d["attempts"]) if d["attempts"] else []
        prev = None
        for a in atts:
            t = ts(a.get("observed_at")) if isinstance(a.get("observed_at"), str) else None
            if (a.get("ordinal") or 0) >= 1:
                reasks += 1
                if t and prev:
                    waits.append(round((t - prev).total_seconds(), 1))
            prev = t or prev
    counts = json.loads(run["counts"]) if run.get("counts") else {}
    snap = json.loads(run["config_snapshot"]) if run.get("config_snapshot") else {}
    return {
        "evidence": ev.name,
        "stage_id": stage["stage_id"],
        "run_id": run["id"],
        "version": stage.get("version"),
        "source_revision": stage.get("source_revision"),
        "lanes": (stage.get("config") or {}).get("lanes"),
        "pilot": snap.get("pilot"),
        "status": run["status"],
        "stop_code": run["stop_code"],
        "submissions": len(led),
        "ledger_states": states,
        "results_settled": sum(int(r["settled_results"] or 0) for r in led if r["state"] == "settled"),
        "usd_settled": round(sum(float(r["settled_usd"] or 0) for r in led if r["state"] == "settled"), 6),
        "unknown_rows": states.get("unknown", 0),
        "usd_unknown_held": round(sum(float(r["worst_usd"] or 0) for r in led if r["state"] == "unknown"), 6),
        "wall_seconds": wall,
        "seconds_with_a_request_in_flight": round(union, 1),
        "seconds_with_none_in_flight": round(wall - union, 1) if wall is not None else None,
        "peak_requests_in_flight": peak,
        "pages_answered": len(pages),
        "pages_counted": sum(1 for p in pages if p["state"] == "completed"),
        "requests_set_aside": len(deferred),
        "set_aside_by_state": {s: sum(1 for d in deferred if d["state"] == s) for s in sorted({d["state"] for d in deferred})},
        "reasks": reasks,
        "reask_wait_seconds": waits,
        "nodes": counts.get("nodes"),
        "gates": counts.get("gates"),
        "verified_records": counts.get("verified"),
        "submissions_per_wall_minute": round(len(led) / (wall / 60), 2) if wall else None,
    }


def main() -> int:
    out = Path(sys.argv[1])
    res = [measure(Path(p)) for p in sys.argv[2:]]
    out.write_bytes((json.dumps(res, indent=1, default=str) + "\n").encode("utf-8"))
    keys = ["evidence", "lanes", "status", "submissions", "usd_settled", "unknown_rows", "wall_seconds",
            "seconds_with_a_request_in_flight", "seconds_with_none_in_flight", "peak_requests_in_flight",
            "pages_answered", "pages_counted", "requests_set_aside", "reasks", "reask_wait_seconds", "nodes",
            "verified_records", "submissions_per_wall_minute"]
    for r in res:
        print(json.dumps({k: r[k] for k in keys}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
