"""The exact incomplete queue of Mariano's Vernon Hills PICKUP after the live stages of release 1.9 (read only; no
request): every listing the shipped CSV names (rows 1-22 through the taxonomy seed's menu nodes, rows 23-27 through
their roots; row 0 is the Coupons route), with the latest state a 1.9 run recorded for it, the size the census of
2026-11-02 measured, what is still needed, and the 1.9 stages in which the listing was completed (each run is
judged on its own: a listing completed in one run and not in a later one is listed with its latest state).

    PSYCOPG_IMPL=python PATH=<pgserver bin>:$PATH <venv python> -X utf8 queue190.py SEED_JSON CENSUS_DIR OUT_CSV
        STAGE=RUN [STAGE=RUN ...]          (stages in time order; a later stage's state of a listing replaces an
                                            earlier one)
"""

from __future__ import annotations

import csv
import glob
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

PORT = Path(r"C:\m8\pg\data\postmaster.pid").read_text().splitlines()[3].strip()
URL = f"postgresql+psycopg://postgres:@127.0.0.1:{PORT}/marianos_q190"
WINDOW = 250


def main(argv: list[str]) -> int:
    seed_path, census_dir, out_path = argv[:3]
    stages = [a.split("=", 1) for a in argv[3:]]
    seed = json.loads(Path(seed_path).read_text("utf-8"))
    census: dict[str, tuple[int, str]] = {}
    for f in sorted(glob.glob(str(Path(census_dir) / "*_D*.json"))):
        d = json.loads(Path(f).read_text("utf-8"))
        for dep in d.get("departments") or []:
            census.setdefault(dep["id"], (dep["count"], d["at"]))
            for c in dep.get("categories") or []:
                census[c["id"]] = (c["count"], d["at"])
    eng = create_engine(URL)
    latest: dict[str, dict[str, object]] = {}
    done_in: dict[str, list[str]] = {}
    with eng.connect() as cx:
        for stage, run in stages:
            rows = cx.execute(text(
                "select taxonomy_id, total_count, organic_upcs, coverage_ratio, status, partition from node_coverage "
                "where run_id = :r"), {"r": run}).mappings().all()
            for r in rows:
                part = r["partition"] if isinstance(r["partition"], dict) else json.loads(r["partition"] or "{}")
                if part.get("parent"):
                    continue  # a brand reading of a listing: counted in its listing's own row
                if r["status"] in ("DONE", "EMPTY") and stage not in done_in.get(str(r["taxonomy_id"]), []):
                    done_in.setdefault(str(r["taxonomy_id"]), []).append(stage)
                latest[str(r["taxonomy_id"])] = {
                    "stage": stage, "run": run, "status": r["status"], "total": r["total_count"],
                    "read": r["organic_upcs"], "ratio": r["coverage_ratio"], "reason": part.get("reason", ""),
                    "readings": len(part.get("partitions") or []),
                }
    out = []
    for row in seed["rows"]:
        i, cat, kind = row["row_index"], row["category"], row["kind"]
        if kind == "coupon_catalogue":
            out.append([i, cat, kind, "", "Coupons", row["url"], "", "", "", "", "", "", "", "",
                        "the Coupons route (offers, not a product listing): read in every run that includes row 0",
                        ""])
            continue
        nodes = row.get("menu_nodes") or [{"taxonomy_id": t, "title": cat, "url": row["url"]} for t in row.get("roots") or []]
        for n in nodes:
            tid = str(n.get("taxonomy_id") or "")
            size = census.get(tid)
            st = latest.get(tid)
            if st is None:
                state, need = "NOT COLLECTED BY 1.9", ("read in a run of its row; brand readings (above the window)"
                                                      if size and size[0] > WINDOW else "read in a run of its row")
            elif st["status"] in ("DONE", "EMPTY"):
                state, need = str(st["status"]), "none in this queue (read again by each scheduled run)"
            else:
                state = str(st["status"])
                if "repeat" in str(st["reason"]):
                    need = "re-ask the repeated page (proposed change) or read again: the page answered with earlier products"
                elif st["readings"]:
                    need = "complete the brand readings"
                else:
                    need = "read again"
            out.append([
                i, cat, kind, tid, n.get("title", ""), n.get("url", ""),
                size[0] if size else "", size[1] if size else "",
                "yes" if size and size[0] > WINDOW else ("no" if size else "not measured"),
                st["stage"] if st else "", st["run"] if st else "", state,
                st["total"] if st else "", st["read"] if st else "", need if not st else (need + (
                    f" ({st['reason']})" if st and st["reason"] else "")),
                " ".join(done_in.get(tid, [])),
            ])
    head = ["csv_row", "row_category", "row_kind", "taxonomy_id", "listing", "listing_url", "census_count",
            "census_at", "above_250_window", "latest_1_9_stage", "latest_1_9_run", "latest_1_9_state",
            "stated_total", "products_read", "still_needed", "completed_by_1_9_stages"]
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(head)
        w.writerows(out)
    counts: dict[str, int] = {}
    for r in out:
        counts[r[11] or "coupons"] = counts.get(r[11] or "coupons", 0) + 1
    ever = sum(1 for r in out if r[15])
    print(json.dumps({"listings": len(out), "by_state": counts, "completed_by_some_1_9_run": ever}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
