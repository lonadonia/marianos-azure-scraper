"""Offline: 1.7.0rc2's exported weight against the 1.8.0rc4 size rules, product by product (no request).

    <x18 venv python> -I size_map180.py SRC_DIR D170_DIR OUT_CSV

The products are the 5,151 that R1 of 1.7.0rc2 saved (2026-10-29, store 53100503 Lakeshore East, In Store: development
evidence), with the size observations read from R1's own stored pages (C:/m6/ev/repro/size_census_rows.json, written by
size_census.py). For each one: the weight 1.7.0rc2 exported (products_retained.json, when the product is there), the
1.8.0rc4 rule, class and exported size. Only the size conflicts are written (rules R3 serving, R4 conflict, R5 unit
denominator): agreement and not-comparable observations are counted, not listed. This applies the size function to
the saved observations; the rest of the record builder is not re-run here.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from marianos_headless.assembly.size_evidence import assess_size, package_weight_measure, price_basis_measure  # noqa: E402

D170 = Path(sys.argv[2])
OUT = Path(sys.argv[3])
rows = json.loads(Path(r"C:\m6\ev\repro\size_census_rows.json").read_text("utf-8"))
kept = {r["upc"]: r for r in json.loads((D170 / "products_retained.json").read_text("utf-8"))}
out = []
tally: Counter[str] = Counter()
for r in rows:
    a = assess_size(r["cfs"], title=r["title"] or "", pid_quantity=r["q"], pid_unit=r["un"],
                    sold_by_weight=str(r.get("sell") or "").upper() == "WEIGHT",
                    basis=price_basis_measure(r.get("price"), r.get("amount"), r.get("per")),
                    package=package_weight_measure(r.get("weight")))
    key = f"{a.resolution.value}/{a.rule}"
    before = kept.get(r["upc"], {}).get("weight")
    if before is None:
        change = "not in 1.7.0rc2's retained export"
    elif before == a.exported:
        change = "unchanged"
    elif a.exported == "":
        change = "emptied (unresolved conflict; observations kept outside the schema)"
    else:
        change = "replaced"
    tally[f"{key} | {change}"] += 1
    if key.startswith(("agree/", "not_comparable/")):
        continue
    out.append({"upc": r["upc"], "product_title": r["title"] or "", "size_slot_observed": r["cfs"],
                "product_data_quantity": r["q"], "product_data_unit": r["un"], "package_weight": r.get("weight") or "",
                "weight_exported_170": "" if before is None else before, "rule_180": a.rule, "class_180": a.resolution.value,
                "weight_exported_180": a.exported, "change": change})
with OUT.open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(out)
for k, v in sorted(tally.items()):
    print(f"{v:>5}  {k}")
print("client product:", [o for o in out if o["upc"] == "0073679800140"])
