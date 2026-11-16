"""Check exported records against the source excerpts they were read from (Python 3.10+, standard library only).

    python3 -I check_sample.py DATA_DIR [UPC ...]           the named UPCs
    python3 -I check_sample.py DATA_DIR --random N [--seed S] N records drawn at random

DATA_DIR holds a run's products.json and source_excerpts.jsonl.gz. For each record: the exported title, prices and
price per measure, beside what the product's own tile in the stored page displayed (its description, its price
element's text, its price-per-measure element's text), read here with Python's own HTML parser, independently of the
collector. The page is named by URL, time and SHA-256: the private original can be produced on request and its hash
checked. Each line ends with "same" or "DIFFERS" for the title and the price per measure, and with whether each
exported price appears in the tile's price text. To check against the live site, open the record's URL (prices and
availability change over time; the excerpt is what the page showed at the stated time).
"""

from __future__ import annotations

import gzip
import json
import random
import sys
from html.parser import HTMLParser
from pathlib import Path

WANT = {"product-description": "description", "product-price": "price",
        "product-price-equivalized-unit-price": "per_measure"}


class Tile(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str | None] = []
        self.found: dict[str, list[str]] = {v: [] for v in WANT.values()}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tid = dict(attrs).get("data-testid")
        if tag in ("br", "img", "input", "meta", "link", "hr", "source", "wbr"):
            return
        self.stack.append(WANT.get(tid or ""))

    def handle_endtag(self, tag: str) -> None:
        if self.stack and tag not in ("br", "img", "input", "meta", "link", "hr", "source", "wbr"):
            self.stack.pop()

    def handle_data(self, data: str) -> None:
        for name in {n for n in self.stack if n}:
            self.found[name].append(data)

    def values(self) -> dict[str, str]:
        return {k: " ".join("".join(v).split()) for k, v in self.found.items()}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")  # type: ignore[union-attr]  # the same bytes on any system
    args = sys.argv[1:]
    data = Path(args.pop(0))
    products = json.loads((data / "products.json").read_text(encoding="utf-8"))
    records = {r["upc"]: r for r in (products if isinstance(products, list) else products.get("products", []))}
    ex = {}
    with gzip.open(data / "source_excerpts.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            ex[d["upc"]] = d
    if args and args[0] == "--random":
        n = int(args[1])
        seed = int(args[3]) if len(args) > 3 and args[2] == "--seed" else 20261116
        upcs = random.Random(seed).sample(sorted(records), min(n, len(records)))
        print(f"{len(upcs)} records drawn at random (seed {seed}) of {len(records)}")
    else:
        upcs = args
    differ = 0
    for upc in upcs:
        r, e = records.get(upc), ex.get(upc)
        print(f"=== {upc}")
        if r is None:
            print("    not in this export")
            continue
        if e is None or not e.get("excerpt"):
            print(f"    no excerpt: {(e or {}).get('why', 'none')}")
            continue
        t = Tile()
        t.feed(e["excerpt"])
        v = t.values()
        title_ok = v["description"] == " ".join(r["product_title"].split())
        ppm_ok = v["per_measure"] == r["ppm"]
        prices = {k: r[k] for k in ("regular_price", "sale_price") if r.get(k)}
        in_tile = {k: (f"${p}" in v["price"]) for k, p in prices.items()}
        differ += (not title_ok) + (not ppm_ok) + sum(1 for ok in in_tile.values() if not ok)
        print(f"    page     {e['page_url']}  observed {e['observed_at']}  sha256 {e['page_sha256']}")
        print(f"    title    export {r['product_title']!r}")
        print(f"             source {v['description']!r}  {'same' if title_ok else 'DIFFERS'}")
        print(f"    prices   export {prices}  source price text {v['price']!r}  "
              + ", ".join(f"{k} {'shown' if ok else 'NOT SHOWN'}" for k, ok in in_tile.items()))
        print(f"    per unit export {r['ppm']!r}  source {v['per_measure']!r}  {'same' if ppm_ok else 'DIFFERS'}")
        print(f"    also     weight {r['weight']!r}, category {r['category']!r} / {r['sub_category']!r}, url {r['url']}")
    print(f"differences: {differ}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
