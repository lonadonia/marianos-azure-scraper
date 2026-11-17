"""Source excerpts of a run's exported records (run on the owner VM with the release's Python, which has selectolax).

    python -I excerpts.py EXPORT_DIR STORE_ROOT OUT.jsonl.gz

For every record of EXPORT_DIR/products.json: the stored listing page it was read from (named by the record's
provenance) is opened, its SHA-256 checked against the provenance, and the product's own tile (the tile whose product
link ends with the record's UPC) is cut out whole. One JSON line per record: the UPC, the record's kind and status
as the provenance gives them (fresh, or carried_forward: an earlier run's observation exported unchanged; since
1.10.0rc6), the run whose stored page it is, the page's fetch id, URL, observation time and SHA-256, the tile's
position, and the tile's HTML exactly as stored. Only the tiles that some record needs are kept in memory. The
summary line counts the records by kind. A record whose page or
tile cannot be found gets a line saying so. The whole pages stay private; each excerpt names the page it was cut from
by its hash, so the private original can be produced on request and checked.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

from selectolax.lexbor import LexborHTMLParser

TILE = '[data-testid^="horizontal-product-card-"], [data-testid^="default-product-card-"]'


def main() -> int:
    exp, root, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    products = json.loads((exp / "products.json").read_text(encoding="utf-8"))
    records = products if isinstance(products, list) else products.get("products", [])
    prov = json.loads((exp / "provenance.json").read_text(encoding="utf-8"))["records"]
    # Only the tiles some record needs are kept (release 1.10.0rc6: a full run's pages held whole would not fit the VM)
    need: dict[str, set[str]] = {}
    for rec in records:
        key = ((prov.get(rec["upc"]) or {}).get("capture") or {}).get("dom_key")
        if key:
            need.setdefault(str(key), set()).add(rec["upc"])
    pages: dict[str, tuple[str, dict[str, object]]] = {}
    counts = {"records": 0, "excerpted": 0, "page_hash_mismatch": 0, "no_page": 0, "no_tile": 0}
    kinds: dict[str, int] = {}
    with gzip.open(out, "wt", encoding="utf-8", newline="\n") as f:
        for rec in records:
            counts["records"] += 1
            upc = rec["upc"]
            p = prov.get(upc) or {}
            cap, obs = p.get("capture") or {}, p.get("observation") or {}
            # Release 1.10.0rc6: the record's kind and status as the provenance gives them, and the run whose stored
            # page this is (a carried record's page belongs to the earlier run that observed it).
            kind = str(p.get("observation_kind"))
            kinds[kind] = kinds.get(kind, 0) + 1
            line: dict[str, object] = {"upc": upc, "observation_kind": p.get("observation_kind"),
                                       "record_status": p.get("status"), "page_run_id": cap.get("run_id"),
                                       "fetch_id": cap.get("page_fetch_id"), "page_url": cap.get("url"),
                                       "observed_at": cap.get("fetched_at"), "page_sha256": cap.get("dom_sha256"),
                                       "position": obs.get("position"), "listing": obs.get("node")}
            key = cap.get("dom_key")
            if not key or not (root / str(key)).exists():
                counts["no_page"] += 1
                f.write(json.dumps({**line, "excerpt": None, "why": "no stored page named or found"}) + "\n")
                continue
            if key not in pages:
                raw = (root / str(key)).read_bytes()
                html = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
                ok = cap.get("dom_sha256") in (hashlib.sha256(raw).hexdigest(), hashlib.sha256(html).hexdigest())
                tiles: dict[str, object] = {}
                wanted = need.get(str(key), set())
                for tile in LexborHTMLParser(html.decode("utf-8", "replace")).css(TILE):
                    for a in tile.css('a[href*="/p/"]'):
                        href = (a.attributes.get("href") or "").split("?")[0].rstrip("/")
                        tid = href.rsplit("/", 1)[-1]
                        if tid in wanted:
                            tiles.setdefault(tid, tile.html)
                pages[str(key)] = ("ok" if ok else "mismatch", tiles)
            state, tiles = pages[str(key)]
            if state != "ok":
                counts["page_hash_mismatch"] += 1
                f.write(json.dumps({**line, "excerpt": None, "why": "the stored page's SHA-256 differs"}) + "\n")
                continue
            html_tile = tiles.get(upc)
            if html_tile is None:
                counts["no_tile"] += 1
                f.write(json.dumps({**line, "excerpt": None, "why": "no tile of the page links to this UPC"}) + "\n")
                continue
            counts["excerpted"] += 1
            f.write(json.dumps({**line, "excerpt": html_tile}, ensure_ascii=False) + "\n")
    print(json.dumps({"out": out.name, "pages": len(pages), **counts, "records_by_kind": kinds}))
    return 0 if counts["page_hash_mismatch"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
