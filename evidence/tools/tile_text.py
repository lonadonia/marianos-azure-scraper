"""PRIVATE (workstation): the visible text of one product's tile on a stored listing page, no network.

    python -I tile_text.py EXPORT_DIR STORED_ROOT OUT.txt UPC [UPC ...]

EXPORT_DIR holds the run's provenance.json; STORED_ROOT is the folder under which the provenance's dom_key resolves
(the run's data root, e.g. ev/L1/stored/.. with dom_key runs/<store>/<run>/live/dom/<fetch>.html.gz, or the folder
holding <run>/live/...). For each UPC: the page, the stored file's SHA-256 against the provenance, and the tile's text
(every text node inside the product card whose link ends with the UPC), and whether the words coupon, clip, save,
digital or cash back appear in it.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

exp, root, out, *upcs = sys.argv[1:]
prov = json.loads((Path(exp) / "provenance.json").read_text(encoding="utf-8"))["records"]
VOID = {"br", "img", "input", "meta", "link", "hr", "source", "wbr", "area", "base", "col", "embed", "param", "track"}
WORDS = re.compile(r"coupon|clip|\bsave\b|digital|cash ?back", re.I)


class Tile(HTMLParser):
    def __init__(self, upc: str) -> None:
        super().__init__(convert_charrefs=True)
        self.upc, self.depth, self.start, self.buf, self.found, self.result = upc, 0, None, [], False, None

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        self.depth += 1
        a = dict(attrs)
        tid = a.get("data-testid") or ""
        if self.start is None and re.match(r"(horizontal|default|vertical)-product-card", tid) or (
            self.start is None and tid.startswith("product-card")
        ):
            self.start, self.buf, self.found = self.depth, [], False
        if self.start is not None and tag == "a" and (a.get("href") or "").split("?")[0].rstrip("/").endswith(self.upc):
            self.found = True

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.start is not None and self.depth == self.start:
            if self.found and self.result is None:
                self.result = " | ".join(t for t in (x.strip() for x in self.buf) if t)
            self.start = None
        self.depth -= 1

    def handle_data(self, data):
        if self.start is not None:
            self.buf.append(data)


def resolve(key: str) -> Path | None:
    r = Path(root)
    for cand in (r / key, r / Path(*Path(key).parts[2:])):
        if cand.exists():
            return cand
    return None


L = []
for upc in upcs:
    p = prov.get(upc)
    L.append(f"=== {upc}")
    if not p:
        L.append("    not in this run's export")
        continue
    c = p["capture"]
    f = resolve(c["dom_key"])
    L.append(f"    page {c['url']}  fetched {c['fetched_at']}  fetch {c['page_fetch_id']}")
    if f is None:
        L.append(f"    stored page not found under {root}")
        continue
    b = f.read_bytes()
    sha = hashlib.sha256(b).hexdigest()
    L.append(f"    stored page sha256 {sha} ({'MATCHES' if sha == c['dom_sha256'] else 'DIFFERS FROM'} the provenance)")
    t = Tile(upc)
    t.feed(gzip.decompress(b).decode("utf-8", errors="replace"))
    L.append(f"    tile text: {t.result!r}")
    if t.result is not None:
        hits = sorted({m.group(0).lower() for m in WORDS.finditer(t.result)})
        L.append(f"    coupon words in the tile: {', '.join(hits) if hits else 'none'}")
    L.append(f"    record flags: {', '.join(p['flags'])}")
Path(out).write_bytes(("\n".join(L) + "\n").encode("utf-8"))
print("\n".join(L))
