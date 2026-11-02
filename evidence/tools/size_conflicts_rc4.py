"""Offline: the 1.8.0rc4 size rules (source folder given as argv[1]) over the 5,151 products saved by R1 of 1.7.0rc2
(2026-10-29, 53100503 In Store, development evidence). Prints the classes. No request."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from marianos_headless.assembly.size_evidence import assess_size, package_weight_measure, parse_size, price_basis_measure  # noqa: E402

rows = json.loads(Path(r"C:\m6\ev\repro\size_census_rows.json").read_text("utf-8"))
c = collections.Counter()
ex = collections.defaultdict(list)
unparsed = collections.Counter()
for r in rows:
    a = assess_size(r["cfs"], title=r["title"] or "", pid_quantity=r["q"], pid_unit=r["un"], sold_by_weight=str(r.get("sell") or "").upper()=="WEIGHT", basis=price_basis_measure(r.get("price"), r.get("amount"), r.get("per")), package=package_weight_measure(r.get("weight")))
    key = f"{a.resolution.value}/{a.rule}"
    c[key] += 1
    ex[key].append((r["upc"], r["cfs"], r["q"], r["un"], (r["title"] or "")[:60], a.exported))
    if parse_size(r["cfs"]) is None and r["cfs"]:
        unparsed[r["cfs"]] += 1
print(c.most_common())
for k, v in ex.items():
    if k.startswith(("agree", "not_comparable/R1")):
        continue
    print("==", k, len(v))
    for x in v[:60]:
        print("  ", x)
print("unparsed", sum(unparsed.values()), unparsed.most_common(30))
