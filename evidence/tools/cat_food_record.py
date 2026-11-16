"""PRIVATE (workstation): Cat Food (CSV row 22, listing 27021) as each run that read it saw it, page by page, from the
runs' own database rows (db_listing_pages.csv) and analyses, no network.

    python -I cat_food_record.py OUT.txt EVIDENCE_DIR [EVIDENCE_DIR ...]

For each run: the stated total, every answer of the listing (page asked, verdict, products shown, new products,
the stored page's SHA-256 and time), the slots and distinct products over the counted pages, every UPC counted on
two pages, and the pages that show 0002310014492 (shown twice, on pages 7 and 8, in Q2 on 2026-11-02).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(1 << 30)
out, *evs = sys.argv[1:]
L = ["Cat Food, CSV row 22, listing 27021 (store 53100502, PICKUP). Before: Q2 (1.8.0rc4, 2026-11-02, run",
     "01M6E5V6CASQ8F00VC8PE9TFYW) read 232 slots holding 231 distinct products, the stated total 232, 0002310014492",
     "shown twice (page 7 slot 24 and page 8 slot 1); evidence/1.9.0/m5_catfood at tag review-1.10.0rc3-20261112.",
     "Columns: state and verdict of the answer (stopped/repeated = the site answered with a page already read, set aside",
     "and asked again by C1); total = the listing's stated result count; products = the listing's own product tiles on",
     "the page (the run's identities); cards-new = the collector's count of cards whose product this listing had not",
     "shown before, sponsored cards included (the figure its repeated-page check uses; not a product count);",
     "sha256 = the stored page's hash as the run recorded it.", ""]
for ev in map(Path, evs):
    rows = [r for r in csv.DictReader((ev / "db_listing_pages.csv").open(encoding="utf-8", newline=""))
            if r["csv_row_index"] == "22" and r["taxonomy_id"] == "27021" and not r["partition_key"]]
    rows.sort(key=lambda r: r["observed_at"])
    rec = json.loads((ev / "stage_record.json").read_text(encoding="utf-8"))
    L.append(f"== {ev.name}: run {rows[0]['run_id'] if rows else '?'}, collector {rec.get('version')} "
             f"({str(rec.get('source_revision'))[:7]})")
    if not rows:
        L.append("   the run did not read this listing")
        L.append("")
        continue
    pages_of: dict[str, list[int]] = defaultdict(list)
    slots = 0
    for r in rows:
        ids = json.loads(r["identities"] or "[]")
        upcs = [i if isinstance(i, str) else (i.get("upc") or i.get("identity") or str(i)) for i in ids]
        L.append(f"   page {r['requested_page']:>2} attempt {r['attempt']}: {r['state']:<9} {r['verdict']:<9} total "
                 f"{r['total'] or '-':>4} products {len(upcs):>3} cards-new {r['new_count']:>3}  {r['observed_at'][:19]}Z  "
                 f"sha256 {r['response_sha256']}")
        if r["state"] == "completed":
            slots += len(upcs)
            for u in upcs:
                pages_of[u].append(int(r["requested_page"]))
    twice = {u: p for u, p in pages_of.items() if len(p) > 1}
    totals = sorted({r["total"] for r in rows if r["total"]})
    L.append(f"   stated total(s): {', '.join(totals)}; counted pages: {sum(r['state'] == 'completed' for r in rows)}; "
             f"slots counted: {slots}; distinct products: {len(pages_of)}; products on two counted pages: "
             f"{json.dumps(twice) if twice else 'none'}")
    L.append(f"   0002310014492: on counted page(s) {pages_of.get('0002310014492', [])}")
    L.append("")
Path(out).write_bytes(("\n".join(L) + "\n").encode("utf-8"))
print("\n".join(x for x in L if x.startswith("==") or "stated total" in x or "0002310014492" in x))
