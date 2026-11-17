"""Every listing's own total and subdivisions as some earlier run of the review recorded them (offline, from the
published run tables): python -I listing_totals.py evidence/runs OUT_JSON. A listing's entry is the first run that
recorded its subdivisions, else the first that recorded its total: [run, total, status, [[child, count]], row]."""
import csv, json, sys, os
from collections import defaultdict
csv.field_size_limit(1 << 30)
base = sys.argv[1]
best = {}  # taxonomy -> (run, total, status, partition children)
for run in sorted(os.listdir(base)):
    d = os.path.join(base, run)
    try:
        runs = list(csv.DictReader(open(f"{d}/db_runs.csv", encoding="utf-8", newline="")))
        cov = list(csv.DictReader(open(f"{d}/db_node_coverage.csv", encoding="utf-8", newline="")))
    except FileNotFoundError:
        continue
    rowof = {}
    for r in runs:
        try:
            for n in json.loads(r["config_snapshot"]).get("plan", {}).get("nodes", []):
                rowof[n["taxonomy_id"]] = n["row_index"]
        except Exception:
            pass
    rows = defaultdict(int)
    for c in cov:
        row = rowof.get(c["taxonomy_id"])
        if row is None or not c["total_count"]:
            continue
        rows[row] += 1
        p = json.loads(c["partition"] or "{}")
        kids = [(q["id"], int(q.get("count") or 0)) for q in p.get("partitions") or []]
        key = c["taxonomy_id"]
        if key not in best or (kids and not best[key][3]):
            best[key] = (run, int(c["total_count"]), c["status"], kids, row)
    print(run, "nodes with totals by row:", dict(sorted(rows.items())))
json.dump({k: v for k, v in best.items()}, open(sys.argv[2], "w", encoding="utf-8"))
print("taxonomies with a total in some run:", len(best))
