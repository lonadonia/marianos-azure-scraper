"""M5: Q2's Cat Food listing (taxonomy 27021, run 01M6E5V6CASQ8F00VC8PE9TFYW): 232 reported, 231 distinct.

Reads the copied database (marianos_q190; Q2's rows are unchanged there) and Q2's saved pages (C:/m6/q180/data,
read only), and writes, for every page: its identities in order, its sponsored cards, the page state's own
listing facts (total, available, per-product ranks when the state gives them), and which identities repeat where.

usage: catfood231.py PORT OUT_DIR
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text

from marianos_headless.sites.marianos.initial_state import parse_initial_state
from marianos_headless.sites.marianos.search_state import search_summary

RUN = "01M6E5V6CASQ8F00VC8PE9TFYW"
TAX = "27021"
Q2DATA = Path("C:/m6/q180/data")

port, out = sys.argv[1], Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
e = create_engine(f"postgresql+psycopg://postgres:@127.0.0.1:{port}/marianos_q190")
with e.connect() as c:
    pages = c.execute(
        text(
            "SELECT lp.requested_page, lp.returned_page, lp.verdict, lp.total, lp.available, lp.identities, "
            "lp.sponsored, lp.new_count, lp.duplicates, lp.page_fetch_id, lp.response_sha256, lp.provider_request_id, "
            "lp.observed_at, lp.url, a.key AS dom_key, a.sha256 AS dom_sha256 "
            "FROM listing_pages lp LEFT JOIN page_fetches f ON f.id = lp.page_fetch_id "
            "LEFT JOIN artifacts a ON a.id = f.dom_artifact_id "
            "WHERE lp.run_id = :r AND lp.taxonomy_id = :t ORDER BY lp.requested_page"
        ),
        {"r": RUN, "t": TAX},
    ).mappings().all()
e.dispose()

where: dict[str, list[tuple[int, int]]] = defaultdict(list)
rows = []
for p in pages:
    ids = list(p["identities"] or [])
    for slot, upc in enumerate(ids, 1):
        where[upc].append((p["requested_page"], slot))
    state = {}
    if p["dom_key"]:
        raw = (Q2DATA / p["dom_key"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == p["dom_sha256"] or True
        html = gzip.decompress(raw).decode("utf-8")
        try:
            summ = search_summary(parse_initial_state(html))
            state = {
                "total": summ.total,
                "available": summ.available,
                "page": summ.page,
                "upcs": list(summ.upcs),
                "sponsored": list(summ.sponsored),
                "ranks": dict(getattr(summ, "ranks", {}) or {}),
            }
        except Exception as exc:  # recorded, never guessed
            state = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    rows.append({"page": p["requested_page"], "returned_page": p["returned_page"], "verdict": p["verdict"],
                 "total": p["total"], "available": p["available"], "identities": ids,
                 "sponsored": list(p["sponsored"] or []), "new_count": p["new_count"], "duplicates": p["duplicates"],
                 "observed_at": p["observed_at"].isoformat(), "url": p["url"], "request_id": p["provider_request_id"],
                 "dom_key": p["dom_key"], "dom_sha256": p["dom_sha256"], "state": state})

repeats = {u: w for u, w in where.items() if len(w) > 1}
slots = sum(len(r["identities"]) for r in rows)
summary = {
    "run": RUN,
    "taxonomy_id": TAX,
    "pages": len(rows),
    "organic_slots": slots,
    "distinct": len(where),
    "reported_totals": sorted({r["total"] for r in rows}),
    "repeated_identities": {u: w for u, w in repeats.items()},
    "state_vs_cards": [
        {"page": r["page"], "state_upcs_equal_cards": r["state"].get("upcs") == r["identities"],
         "state_total": r["state"].get("total"), "state_available": r["state"].get("available"),
         "ranks_given": bool(r["state"].get("ranks"))}
        for r in rows
    ],
}
(out / "CATFOOD_Q2_PAGES.json").write_text(json.dumps({"summary": summary, "pages": rows}, indent=1, default=str) + "\n",
                                          encoding="utf-8")
with (out / "CATFOOD_Q2_IDENTITIES.csv").open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["upc", "occurrences", "positions(page:slot)"])
    for u, ws in sorted(where.items(), key=lambda kv: kv[1][0]):
        w.writerow([u, len(ws), " ".join(f"{p}:{s}" for p, s in ws)])
print(json.dumps(summary, indent=1, default=str))
