"""Randomized record check (offline, standard library only): draws N records of products_fresh.json and shows each
one beside the text of its product card in the page the run stored, with the stored page's SHA-256 checked against
the record's provenance. No request is sent.

    python3 check_records.py <products_fresh.json> <run folder of the evidence archive> [N] [seed]

The run folder is runs/<run id> of MARIANOS_EVIDENCE_1.8.0rc5.zip: runs/01M6E5V6CASQ8F00VC8PE9TFYW for Q2 (it holds
db/ and data/, with data/live/dom/<page fetch id>.html.gz and data/exports/provenance.json). Without a seed the draw
is random each time; the seed used is printed so the draw can be repeated. Adapted from random_record_check.py of
the 1.7.0rc2 evidence: the page is found through the provenance's own storage key, and both card variants of the
site (product-card-N and mini-product-card-N) are read.
"""

import gzip
import hashlib
import html
import json
import random
import re
import sys
from pathlib import Path

FIELDS = ("product_title", "weight", "regular_price", "sale_price", "volume_deals_description", "volume_deals_price",
          "digital_deals_description", "ppm", "store_name", "crawl_date")
CARD = re.compile(r'data-testid="(?:mini-)?product-card-\d+"')


def card_text(page: str, upc: str) -> str:
    """The visible text of the product's card in the stored page (from its card marker to the next one)."""
    i = page.find(upc)
    if i < 0:
        return "(UPC not found in the page)"
    starts = [m.start() for m in CARD.finditer(page, 0, i)]
    start = starts[-1] if starts else max(0, i - 4000)
    nxt = CARD.search(page, i)
    chunk = page[start: nxt.start() if nxt else i + 6000]
    chunk = re.sub(r"<script.*?</script>|<style.*?</style>", " ", chunk, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", chunk))
    return re.sub(r"\s+", " ", text).strip()[:900]


def main() -> int:
    products = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    run = Path(sys.argv[2])
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else random.SystemRandom().randrange(10**9)
    prov = json.loads((run / "data/exports/provenance.json").read_text(encoding="utf-8"))["records"]
    print(f"seed {seed}; {n} of {len(products)} records")
    failures = 0
    for rec in random.Random(seed).sample(products, min(n, len(products))):
        p = prov[rec["upc"]]
        cap = p["capture"]
        page_file = run / "data/live/dom" / Path(cap["dom_key"]).name
        stored = page_file.read_bytes()
        sha_ok = hashlib.sha256(stored).hexdigest() == cap["dom_sha256"]  # the hash of the stored object
        failures += not sha_ok
        raw = gzip.decompress(stored) if page_file.suffix == ".gz" else stored
        obs = p.get("observation") or {}
        print("=" * 100)
        print(f"UPC {rec['upc']}  status {p['status']}  observed {obs.get('observed_at')}  segment {obs.get('segment')}")
        print(f"page {page_file.name}  SHA-256 matches the provenance: {sha_ok}  ({cap['url']})")
        for f in FIELDS:
            print(f"  {f:26} {rec[f]!r}")
        print(f"  url                        {rec['url']}")
        print("card text in the stored page:")
        print("  " + card_text(raw.decode("utf-8", "replace"), rec["upc"]))
    print("=" * 100)
    print("page hash mismatches:", failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
