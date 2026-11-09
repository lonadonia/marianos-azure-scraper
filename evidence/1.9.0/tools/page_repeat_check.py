"""For listing answers (the provider's raw answer .raw.gz, or the collector's stored page .html.gz): which products the
tiles show (in order), the page state's search ranks with their UPCs, and loadedPages. Read only.

usage: python -I page_repeat_check.py FILE [FILE ...]
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

TILE = re.compile(r'data-testid="(?:horizontal|default)-product-card-(\d+)"')
LINK = re.compile(r'href="/p/[^"]+/(\d{13})"')
RANK = re.compile(r'"searchEngineRank":(\d+),"upc":"(\d{13})"')
LOADED = re.compile(r'"loadedPages":\[([0-9,]*)\]')
HREF = re.compile(r'"href":"(https://www\.marianos\.com/[^"]+)"')


def html_of(p: Path) -> tuple[str, dict]:
    b = gzip.decompress(p.read_bytes())
    meta: dict = {}
    if p.name.endswith(".raw.gz"):
        j = json.loads(b)
        res = j.get("results") or [j]
        html = res[0].get("html") or res[0].get("content", "")
        meta = {k: res[0].get(k) for k in ("status_code", "url", "page", "run_js", "rendered") if k in res[0]}
        meta["params"] = {k: v for k, v in (j.get("params") or {}).items() if k in ("url", "run_js", "query", "page")}
        if not isinstance(html, str):
            html = json.dumps(html)
        return html, meta
    return b.decode("utf-8", "replace"), meta


def main(files: list[str]) -> None:
    for f in files:
        p = Path(f)
        html, meta = html_of(p)
        seen: list[str] = []
        for u in LINK.findall(html):
            if u not in seen:
                seen.append(u)
        ranks = RANK.findall(html)
        print(json.dumps({
            "file": p.name, "meta": meta, "href": HREF.findall(html)[:1], "loadedPages": LOADED.findall(html)[:1],
            "tiles": len(TILE.findall(html)), "tile_products": len(seen), "first_tile_upcs": seen[:3],
            "last_tile_upc": seen[-1:], "rank_first": ranks[:1], "rank_last": ranks[-1:],
            "rank_upcs": [u for _, u in ranks],
        }))


if __name__ == "__main__":
    main(sys.argv[1:])
