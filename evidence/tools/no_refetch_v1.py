"""PRIVATE (workstation): FIRST VERSION of no_refetch.py (kept to reproduce its output; replaced about 18:10Z on
2026-11-16 because its rule took a deliberate C1 re-ask whose own answer was malformed for a re-fetch).

    python -I no_refetch_v1.py DB_LISTING_PAGES.csv DB_COLLECTION_SEGMENTS.csv DB_DEFERRED_REQUESTS.csv OUT.txt

A request is keyed by (category source, taxonomy, partition, route, requested page, requested filter). For every key
with a row in state "completed", a row of the same key observed later is either a deliberate C1 re-ask (state
"reasked", and the run holds a request set aside for that same key: a first page above the 250-result window answered
without the filters needed to subdivide it is counted, then asked again for its filters) or a re-fetch of a completed
page. Also lists, per segment, its rows, its completed rows, and the earliest and latest observation. Exit 0 when
there is no re-fetch, 1 otherwise.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

csv.field_size_limit(1 << 30)
pages_path, segs_path, deferred_path, out_path = sys.argv[1:]
rows = list(csv.DictReader(Path(pages_path).open(encoding="utf-8", newline="")))
segs = {r["id"]: r for r in csv.DictReader(Path(segs_path).open(encoding="utf-8", newline=""))}
deferred = list(csv.DictReader(Path(deferred_path).open(encoding="utf-8", newline="")))
set_aside = {(d["category_source_id"], d["taxonomy_id"], d["partition_key"], d["requested_page"],
              d["requested_filter"]): d["kind"] for d in deferred}


def key(r: dict[str, str]) -> tuple[str, ...]:
    return (r["category_source_id"], r["taxonomy_id"], r["partition_key"], r["route"], r["requested_page"],
            r["requested_filter"])


rows.sort(key=lambda r: r["observed_at"])
first_done: dict[tuple[str, ...], dict[str, str]] = {}
refetch, reasks = [], []
for r in rows:
    k = key(r)
    if k in first_done:
        kind = set_aside.get((k[0], k[1], k[2], k[4], k[5]))
        (reasks if r["state"] == "reasked" and kind else refetch).append((first_done[k], r, kind))
    if r["state"] == "completed" and k not in first_done:
        first_done[k] = r
by_seg: dict[str, list[dict[str, str]]] = defaultdict(list)
for r in rows:
    by_seg[r["segment_id"]].append(r)
L = [f"listing-page rows of the run: {len(rows)}; states {dict(Counter(r['state'] for r in rows))}",
     f"distinct requests completed: {len(first_done)}", "", "per segment (in order of its first row):"]
for sid, rs in sorted(by_seg.items(), key=lambda kv: kv[1][0]["observed_at"]):
    s = segs.get(sid, {})
    L.append(f"  {sid}: rows {len(rs)}, completed {sum(r['state'] == 'completed' for r in rs)}, "
             f"first {rs[0]['observed_at']}, last {rs[-1]['observed_at']}; segment {s.get('started_at', '?')} -> "
             f"{s.get('ended_at', '?')} {s.get('end_state', '?')} {s.get('stop_code', '')} ({s.get('trigger', '')})")
L.append("")
L.append(f"deliberate C1 re-asks of a completed page (state reasked, a request set aside for the same key): "
         f"{len(reasks)}")
for a, b, kind in reasks:
    L.append(f"  {key(a)}: completed {a['observed_at']} (segment {a['segment_id']}), asked again "
             f"{b['observed_at']} (segment {b['segment_id']}, set aside as {kind}): {b['detail'][:120]}")
L.append("")
if refetch:
    L.append(f"RE-FETCHED AFTER COMPLETION: {len(refetch)}")
    for a, b, kind in refetch[:50]:
        L.append(f"  {key(a)}: completed {a['observed_at']} (segment {a['segment_id']}), asked again "
                 f"{b['observed_at']} (segment {b['segment_id']}, state {b['state']})")
else:
    L.append("no completed page was re-fetched: apart from the deliberate C1 re-asks above, no request has a row "
             "after its completed one, in any segment")
Path(out_path).write_bytes(("\n".join(L) + "\n").encode("utf-8"))
print("\n".join(L[-3:]))
raise SystemExit(1 if refetch else 0)
