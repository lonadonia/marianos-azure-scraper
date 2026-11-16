"""PRIVATE (workstation): the client's named offer and size products in one run's export, no network.

    python -I named_offers.py EXPORT_DIR OUT.txt

For Cutwater Espresso Martini (0081675102373, "Buy 1 Save $1"), The Finnish Long Drink (0086001079386, "Buy 1 Save $2"),
Nutrl Vodka Hard Seltzer (0001820020352, "Buy 1 Save $2") and the Avocado Green Goddess Dip & Spread (0073679800140,
serving "2 tbsp" against the pack's 8 OUNCES): whether the run exported the product; if so its title, weight, prices,
volume and digital fields, flags and missing-field reasons, its page and the page's SHA-256, and every offer the run
kept for it in offers.json (text, kind, flags). Absent products are listed as absent, with nothing inferred.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

exp, out = Path(sys.argv[1]), Path(sys.argv[2])
NAMED = {
    "0081675102373": 'Cutwater Espresso Martini ("Buy 1 Save $1": a one-unit condition, not a volume offer)',
    "0086001079386": 'The Finnish Long Drink ("Buy 1 Save $2": a one-unit condition, not a volume offer)',
    "0001820020352": 'Nutrl Vodka Hard Seltzer ("Buy 1 Save $2": a one-unit condition, not a volume offer)',
    "0073679800140": 'Avocado Green Goddess Dip & Spread (weight is the pack, 8 OUNCES, not the serving "2 tbsp")',
}
recs = {r["upc"]: r for r in json.loads((exp / "products.json").read_text(encoding="utf-8"))}
prov = json.loads((exp / "provenance.json").read_text(encoding="utf-8"))["records"]
offers = json.loads((exp / "offers.json").read_text(encoding="utf-8"))
L = [f"Export: {exp.as_posix()} ({len(recs)} records, {len(offers)} offers kept)", ""]
for upc, what in NAMED.items():
    L.append(f"=== {upc}  {what}")
    r, p = recs.get(upc), prov.get(upc)
    if r is None:
        L.append("    not exported by this run (its listing was not read, or the product was not shown)")
        continue
    c = (p or {}).get("capture") or {}
    L.append(f"    title    {r['product_title']!r}")
    L.append(f"    weight   {r['weight']!r}")
    L.append(f"    prices   regular {r['regular_price']!r} sale {r['sale_price']!r} ppm {r['ppm']!r}")
    L.append(f"    volume   {r['volume_deals_description']!r} {r['volume_deals_price']!r}")
    L.append(f"    digital  {r['digital_deals_description']!r} {r['digital_deals_price']!r}")
    L.append(f"    category {r['category']!r} / {r['sub_category']!r}")
    if p:
        L.append(f"    record   {p['observation_kind']}, {p['status']}; flags {', '.join(p['flags']) or '-'}")
        miss = (p.get("observation") or {}).get("missing") or p.get("missing") or {}
        for k in ("weight", "volume_deals_description", "volume_deals_price", "sale_price"):
            if k in miss:
                L.append(f"    missing  {k}: {miss[k]}")
        L.append(f"    page     {c.get('url')}  fetched {c.get('fetched_at')}  sha256 {c.get('dom_sha256')}")
    mine = [o for o in offers if o.get("upc") == upc]
    for o in mine:
        L.append(f"    offer    {o.get('text')!r} kind {o.get('kind')} source {o.get('source')} price "
                 f"{o.get('explicit_price')!r} flags {', '.join(o.get('flags') or []) or '-'}")
    if not mine:
        L.append("    offer    none kept for this product")
out.write_bytes(("\n".join(L) + "\n").encode("utf-8"))
print("\n".join(L))
