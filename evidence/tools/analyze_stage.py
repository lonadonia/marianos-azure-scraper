"""PRIVATE (workstation): analysis of one stage's evidence folder (from stage_evidence.sh), no network.

    python -I analyze_stage.py EVIDENCE_DIR

Writes EVIDENCE_DIR/analysis/{LISTINGS.csv, REASKS.csv, ANALYSIS.json} and prints a summary. Counts come from the
database rows the run wrote (listing_pages, deferred_requests) and the collector's own coverage files; nothing is
inferred that the rows do not state.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

csv.field_size_limit(1 << 30)
EV = Path(sys.argv[1])
OUT = EV / "analysis"
OUT.mkdir(exist_ok=True)


def rows(name: str) -> list[dict[str, str]]:
    p = EV / name
    return list(csv.DictReader(p.open(encoding="utf-8", newline=""))) if p.exists() else []


def js(v: str, default: object) -> object:
    try:
        return json.loads(v) if v not in ("", None) else default
    except json.JSONDecodeError:
        # PostgreSQL arrays exported by \copy as {a,b}
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            inner = v[1:-1]
            return [x.strip('"') for x in inner.split(",")] if inner else []
        return default


def ts(v: str) -> datetime | None:
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


pages = rows("db_listing_pages.csv")
deferred = rows("db_deferred_requests.csv")
by_listing: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
for p in pages:
    by_listing[(p["csv_row_index"], p["taxonomy_id"], p["partition_key"])].append(p)

listings = []
for (row, tax, part), ps in sorted(by_listing.items(), key=lambda kv: (int(kv[0][0]), kv[0][1], kv[0][2])):
    ps.sort(key=lambda p: (p["observed_at"], int(p["requested_page"])))
    counted = [p for p in ps if p["state"] == "completed"]
    slots: list[str] = []
    where: dict[str, list[int]] = defaultdict(list)
    for p in counted:
        ids = js(p["identities"], [])
        slots.extend(ids)
        for i in ids:
            where[i].append(int(p["requested_page"]))
    dup = {k: v for k, v in where.items() if len(v) > 1}
    totals = [int(p["total"]) for p in ps if p["total"] not in ("", None)]
    listings.append({
        "csv_row": row, "taxonomy_id": tax, "partition": (json.dumps(js(ps[0]["requested_filter"], {}), sort_keys=True)
                                                       if part else ""),
        "stated_total_last": totals[-1] if totals else "", "stated_totals_seen": sorted(set(totals)),
        "answers": len(ps), "pages_counted": len(counted),
        "states": dict(sorted({s: sum(1 for p in ps if p["state"] == s) for s in {p["state"] for p in ps}}.items())),
        "verdicts": dict(sorted({v: sum(1 for p in ps if p["verdict"] == v) for v in {p["verdict"] for p in ps}}.items())),
        "slots_counted": len(slots), "distinct_counted": len(set(slots)),
        "duplicates_across_counted_pages": {k: v for k, v in sorted(dup.items())},
        "store_checks": sorted({p["store_check"] for p in ps}),
        "locations": sorted({p["location_id"] for p in ps if p["location_id"]}),
        "modalities": sorted({p["modality"] for p in ps if p["modality"]}),
        "first_observed": ps[0]["observed_at"], "last_observed": ps[-1]["observed_at"],
    })

with (OUT / "LISTINGS.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(listings[0]) if listings else ["csv_row"], lineterminator=chr(10))
    w.writeheader()
    for r in listings:
        w.writerow({k: (json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v) for k, v in r.items()})

reasks = []
recovered_new = 0
for d in deferred:
    atts = js(d["attempts"], [])
    prev = None
    for a in atts:
        t = ts(a.get("observed_at")) if isinstance(a.get("observed_at"), str) else None
        gap = round((t - prev).total_seconds(), 1) if (t and prev) else ""
        ret = a.get("returned") if isinstance(a.get("returned"), dict) else {}
        reasks.append({
            "csv_row": d["csv_row_index"], "taxonomy_id": d["taxonomy_id"], "page": d["requested_page"],
            "kind": d["kind"], "request_state": d["state"], "reasks_dispatched": d["reasks_dispatched"],
            "ordinal": a.get("ordinal"), "role": a.get("role"), "answered": a.get("answered"),
            "observed_at": a.get("observed_at") if isinstance(a.get("observed_at"), str) else "",
            "seconds_after_previous_answer": gap,
            "returned_page": ret.get("page") if not isinstance(ret.get("page"), dict) else "unavailable",
            "returned_listing": ret.get("listing") if not isinstance(ret.get("listing"), dict) else "unavailable",
            "returned_store": ret.get("store_id") if not isinstance(ret.get("store_id"), dict) else "unavailable",
            "returned_fulfillment": ret.get("fulfillment") if not isinstance(ret.get("fulfillment"), dict) else "unavailable",
            "verdict": a.get("verdict"), "new": a.get("new"), "overlap": a.get("overlap"), "counted": a.get("counted"),
            "unique_before": a.get("unique_before"), "unique_after": a.get("unique_after"),
            "capture_sha256": (a.get("capture") or {}).get("sha256") if isinstance((a.get("capture") or {}).get("sha256"), str) else "",
            "provider_request_id": a.get("provider_request_id") if isinstance(a.get("provider_request_id"), str) else "",
            "original_reason": d["original_reason"][:200], "outcome": d["outcome"][:200],
        })
        if a.get("ordinal", 0) >= 1 and a.get("counted"):
            recovered_new += int(a.get("new") or 0)
        prev = t or prev

with (OUT / "REASKS.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(reasks[0]) if reasks else ["csv_row"], lineterminator=chr(10))
    w.writeheader()
    w.writerows(reasks)


def gates(path: Path) -> dict[str, object]:
    found: dict[str, object] = {}
    if not path.exists():
        return found

    def walk(o: object, trail: str = "") -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(k, str) and k[:1] == "G" and k[1:].isdigit():
                    found[f"{trail}{k}"] = v if not isinstance(v, (dict, list)) else (v.get("status") if isinstance(v, dict) else v)
                walk(v, f"{trail}{k}." if k in ("gates",) else trail)
        elif isinstance(o, list):
            for v in o:
                walk(v, trail)

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            walk(json.loads(line))
        except json.JSONDecodeError:
            continue
    return found


summary = {
    "evidence": str(EV),
    "listing_answers": len(pages),
    "listings_and_partitions": len(listings),
    "deferred_requests": len(deferred),
    "deferred_by_state": {s: sum(1 for d in deferred if d["state"] == s) for s in sorted({d["state"] for d in deferred})},
    "reasks_answered": sum(1 for r in reasks if (r["ordinal"] or 0) >= 1 and r["answered"]),
    "distinct_new_products_from_counted_reasks": recovered_new,
    "min_seconds_between_answers_of_a_request": min((r["seconds_after_previous_answer"] for r in reasks
                                                     if r["seconds_after_previous_answer"] != ""), default=None),
    "distinct_identities_all_counted_pages": len({i for p in pages if p["state"] == "completed" for i in js(p["identities"], [])}),
    "validation_report": (lambda v: {"status": v.get("status"), "dataset": v.get("dataset"),
                                     "gates": (v.get("counts") or {}).get("gates"),
                                     "nodes": (v.get("counts") or {}).get("nodes")})(
        json.loads((EV / "export" / "validation_report.json").read_text(encoding="utf-8"))
        if (EV / "export" / "validation_report.json").exists() else {}),
    "cat_food_27021": [r for r in listings if r["taxonomy_id"] == "27021"],
    "upc_0002310014492_pages": sorted({int(p["requested_page"]) for p in pages if p["state"] == "completed"
                                       and "0002310014492" in js(p["identities"], [])}),
    "listings_with_duplicate_slots": [{k: r[k] for k in ("csv_row", "taxonomy_id", "partition", "stated_total_last",
                                                         "slots_counted", "distinct_counted",
                                                         "duplicates_across_counted_pages")}
                                      for r in listings if r["duplicates_across_counted_pages"]],
    "store_checks": sorted({p["store_check"] for p in pages}),
    "locations": sorted({p["location_id"] for p in pages if p["location_id"]}),
    "modalities": sorted({p["modality"] for p in pages if p["modality"]}),
}
(OUT / "ANALYSIS.json").write_bytes((json.dumps(summary, indent=1, default=str) + "\n").encode("utf-8"))
print(json.dumps(summary, indent=1, default=str)[:6000])
print("\nLISTINGS:")
for r in listings:
    print(f"row {r['csv_row']:>2} {r['taxonomy_id']:<8} {r['partition'][:40]:<40} total={r['stated_total_last']!s:<5} "
          f"counted_pages={r['pages_counted']:<3} slots={r['slots_counted']:<4} distinct={r['distinct_counted']:<4} "
          f"states={r['states']} dups={len(r['duplicates_across_counted_pages'])}")
