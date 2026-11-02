"""The 22-field contract of an exported products file (offline): field order, string values, no nulls,
gupc and unit_price empty, UPC 13 digits (leading zeros kept), marianos.com product URLs and kroger.com
product pictures, price format, PPM with its unit, crawl_date format, duplicates (by UPC and URL),
approximate-weight wording. ``marianos-collector validate-export`` runs it."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from marianos_headless.core.schema import OUTPUT_FIELDS

PRICE = re.compile(r"^\d+\.\d{2}$")
PPM = re.compile(r"^\$?\d*\.?\d+\s*(?:¢|c)?\s*/\s*(?:\d+\s*)?[a-z][a-z .]*$", re.I)
UPC = re.compile(r"^\d{13}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
APPROX = re.compile(r"\bapprox(?:imately|\.)?\b|\babout\b|~", re.I)


def check(path: Path) -> dict[str, Any]:
    rows = json.loads(path.read_text("utf-8"))
    problems: Counter[str] = Counter()
    for r in rows:
        if list(r) != list(OUTPUT_FIELDS):
            problems["field order"] += 1
        for k, v in r.items():
            if v is None:
                problems[f"null {k}"] += 1
            elif not isinstance(v, str):
                problems[f"not a string {k}"] += 1
        if r.get("gupc") or r.get("unit_price"):
            problems["gupc or unit_price not empty"] += 1
        if not UPC.match(r.get("upc", "")):
            problems["upc not 13 digits"] += 1
        if not r.get("url", "").startswith("https://www.marianos.com/p/"):
            problems["url host"] += 1
        if r.get("image_url") and not r["image_url"].startswith("https://www.kroger.com/product/images/"):
            problems["image host"] += 1
        for f in ("regular_price", "sale_price", "volume_deals_price", "digital_deals_price"):
            if r.get(f) and not PRICE.match(r[f]):
                problems[f"{f} format"] += 1
        if r.get("ppm") and not PPM.match(r["ppm"]):
            problems["ppm format"] += 1
        if not DATE.match(r.get("crawl_date", "")):
            problems["crawl_date format"] += 1
        if APPROX.search(r.get("weight", "")):
            problems["approximate weight wording"] += 1
    upcs = Counter(r["upc"] for r in rows if r["upc"])
    urls = Counter(r["url"] for r in rows)
    return {
        "file": path.name,
        "rows": len(rows),
        "problems": dict(problems),
        "duplicate_upc": sum(v - 1 for v in upcs.values() if v > 1),
        "duplicate_url": sum(v - 1 for v in urls.values() if v > 1),
        "leading_zero_upcs": sum(1 for u in upcs if u.startswith("0")),
        "populated": {f: sum(1 for r in rows if r[f]) for f in OUTPUT_FIELDS},
        "categories": dict(Counter(r["category"] for r in rows)),
        "ppm_units": dict(Counter(r["ppm"].split("/")[-1].strip() for r in rows if r["ppm"])),
        "passed": not problems and not any(v > 1 for v in upcs.values()),
    }
