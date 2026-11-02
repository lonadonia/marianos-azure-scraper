"""Offline: the digital offers Q1c exported that Q2 did not, checked in each run's own stored page (no request).

    python -I offer_change180.py OUT_CSV

For every product whose digital_deals_description differs between Q1c (12:38-12:52Z) and Q2 (13:05-14:10Z), both at
Vernon Hills Pickup: the text each export holds, and how often the Q1c offer text occurs in the page each run stored
for the product (the page its provenance names). A text present in Q1c's page and absent from Q2's is an offer the
site stopped showing between the runs; a text present in Q2's page with an empty Q2 field would be a collector defect.
"""

import csv
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

E1 = Path(r"C:\m6\q180\exports\01M6E49AHDXSQA04JQZ0HZ40GH")
E2 = Path(r"C:\m6\q180\exports\01M6E5V6CASQ8F00VC8PE9TFYW")
DATA = Path(r"C:\m6\q180\data")


def load(e: Path) -> tuple[dict, dict]:
    recs = {r["upc"]: r for r in json.loads((e / "products.json").read_text("utf-8"))}
    prov = json.loads((e / "provenance.json").read_text("utf-8"))["records"]
    return recs, prov


def page_text(prov: dict) -> tuple[str, str]:
    cap = prov["capture"]
    raw = (DATA / cap["dom_key"]).read_bytes()
    return gzip.decompress(raw).decode("utf-8", "replace"), cap["url"]


r1, p1 = load(E1)
r2, p2 = load(E2)
rows = []
for upc in sorted(set(r1) & set(r2)):
    a, b = r1[upc]["digital_deals_description"], r2[upc]["digital_deals_description"]
    if a == b:
        continue
    texts = [o["text"] for o in (p1[upc].get("offers") or []) if o.get("kind") == "digital"] or [a]
    h1, u1 = page_text(p1[upc])
    h2, u2 = page_text(p2[upc])
    t = texts[0]
    rows.append({"upc": upc, "product_title": r2[upc]["product_title"], "q1c_digital": a, "q2_digital": b,
                 "offer_text": t, "q1c_page": u1, "q1c_page_occurrences": h1.count(t),
                 "q2_page": u2, "q2_page_occurrences": h2.count(t),
                 "q2_missing_reason": (p2[upc].get("missing") or {}).get("digital_deals_description", ""),
                 "reading": ("offer no longer shown on the site at Q2's time" if h1.count(t) and not h2.count(t)
                             else "CHECK: offer text still in Q2's page" if h2.count(t) else "CHECK: offer text not in Q1c's page")})
out = Path(sys.argv[1])
with out.open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
print(len(rows), Counter(r["reading"] for r in rows), Counter(r["offer_text"] for r in rows))
