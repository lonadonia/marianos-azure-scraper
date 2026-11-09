"""M3 census: every exported PPM string against the product's own displayed prices and stated pack (comparisons
only; no PPM is computed and no exported value is changed).

Patterns (diagnostic sidecar flags):
- PPM_EQUALS_ITEM_PRICE: the exported (displayed) per-unit amount equals the item's displayed regular or sale price
  while the product's own stated pack quantity is not 1.
- PPM_UNIT_FAMILY_MISMATCH: the displayed per-unit unit is a measure (oz, lb, fl oz, ...) while the product's own
  stated pack unit is a count (EACH), or the displayed unit is a count while the stated pack unit is a measure.
Usage: python -I ppm_census.py <run evidence dir> <out csv>
"""

from __future__ import annotations

import csv
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

PPM = re.compile(r"^\$(?P<amount>\d[\d,]*(?:\.\d+)?)\s*/\s*(?P<unit>[A-Za-z][A-Za-z .]*)$")
COUNT_WORDS = {"each", "ea", "ct", "count"}
COUNT_UNITS = {"EACH", "COUNT", "CT", "EA"}


def dec(x):
    try:
        return Decimal(str(x).replace(",", "").strip()) if str(x).strip() else None
    except (InvalidOperation, ValueError):
        return None


def main() -> int:
    run_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    exp = run_dir / "data" / "exports"
    products = {r["upc"]: r for r in json.loads((exp / "products.json").read_text(encoding="utf-8"))}
    prov = json.loads((exp / "provenance.json").read_text(encoding="utf-8"))["records"]
    rows = []
    counts = {"records": 0, "with_ppm": 0, "unparsed_ppm": 0, "PPM_EQUALS_ITEM_PRICE": 0,
              "PPM_UNIT_FAMILY_MISMATCH": 0}
    for upc, rec in products.items():
        counts["records"] += 1
        if not rec["ppm"]:
            continue
        counts["with_ppm"] += 1
        m = PPM.match(rec["ppm"].strip())
        if m is None:
            counts["unparsed_ppm"] += 1
            continue
        amount, unit = dec(m.group("amount")), m.group("unit").strip().lower()
        sc = (prov.get(upc) or {}).get("source_check") or {}
        pack_unit = str(sc.get("size_unit") or "").upper()
        qty = dec(sc.get("size_quantity"))
        prices = {p for p in (dec(rec["regular_price"]), dec(rec["sale_price"])) if p is not None}
        flags = []
        if amount is not None and amount in prices and qty is not None and qty != 1:
            flags.append("PPM_EQUALS_ITEM_PRICE")
        if pack_unit:
            if (unit not in COUNT_WORDS) == (pack_unit in COUNT_UNITS):
                flags.append("PPM_UNIT_FAMILY_MISMATCH")
        for fl in flags:
            counts[fl] += 1
        if flags:
            rows.append({"upc": upc, "title": rec["product_title"], "exported_ppm": rec["ppm"],
                         "exported_weight": rec["weight"], "regular_price": rec["regular_price"],
                         "sale_price": rec["sale_price"], "stated_pack_quantity": sc.get("size_quantity"),
                         "stated_pack_unit": sc.get("size_unit"),
                         "stated_unit_price_text": ";".join(sc.get("unit_price_text") or []),
                         "flags": ";".join(flags), "record_status": (prov.get(upc) or {}).get("status")})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["upc"], lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(counts), len(rows), "flagged rows")
    for r in rows:
        print(r["upc"], r["flags"], r["exported_ppm"], "|", r["exported_weight"], "| price", r["regular_price"],
              r["sale_price"], "| pack", r["stated_pack_quantity"], r["stated_pack_unit"], "|", r["title"][:45])
    return 0


if __name__ == "__main__":
    sys.exit(main())
