"""Offline: 1.7.0rc2's exported volume-deal texts re-read with the 1.8.0rc4 volume rule (no request).

    <x18 venv python> -I promo_census180.py SRC_DIR D170_DIR OUT_CSV

SRC_DIR is the extracted 1.8.0rc4 source's src folder. For every record of 1.7.0rc2's products_retained.json whose
volume_deals_description is not empty, the offer text (the description without its "(Exp. ...)" suffix) goes through
the 1.8.0rc4 functions is_volume_text and required_quantity. This re-reads exported text only: the whole record (the
clip tags, the offer's modality, the digital field) is not rebuilt here, and nothing is collected.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from marianos_headless.assembly.offers import is_volume_text, required_quantity  # noqa: E402

D170 = Path(sys.argv[2])
OUT = Path(sys.argv[3])
EXP = re.compile(r"\s*\((?:Exp\.|Expires)[^)]*\)\s*$", re.I)

rows = json.loads((D170 / "products_retained.json").read_text("utf-8"))
out = []
for r in rows:
    desc = r.get("volume_deals_description", "")
    if not desc:
        continue
    for part in [p.strip() for p in desc.split(" | ") if p.strip()]:
        text = EXP.sub("", part)
        vol = is_volume_text(text)
        out.append({"upc": r["upc"], "product_title": r["product_title"], "category": r["category"],
                    "volume_deals_description_170": desc, "offer_text": text,
                    "required_quantity_180": required_quantity(text) or "", "volume_180": "yes" if vol else "no",
                    "volume_deals_price_170": r.get("volume_deals_price", ""),
                    "outcome_180": "stays volume" if vol else "not a volume deal under 1.8.0 (volume fields empty)",
                    "crawl_date": r.get("crawl_date", "")})
with OUT.open("w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(out)
print("records with a volume deal in 1.7.0rc2:", len({o["upc"] for o in out}), "offers:", len(out))
print(Counter(o["outcome_180"] for o in out))
moved = Counter(o["offer_text"] for o in out if o["volume_180"] == "no")
print("texts moved out of volume:", moved.most_common(25))
print("client UPCs:", [(o["upc"], o["offer_text"], o["volume_180"]) for o in out if o["upc"] in ("0081675102373", "0086001079386")])
