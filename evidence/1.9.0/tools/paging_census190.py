"""Every listing answer of the given runs, as the collector stored it: when it was asked, the page asked for, what the
provider says about rendering, the tiles it carries, the products its page state ranks and whether they are the
products of the listing's page 1 in the same run (the repeat seen since 2026-11-06); the page's own search id,
stated total and reachable count, and whether its state names a brand filter (productsInfo.brands). Read only: the stage database
(page fetches and the provider's metadata recorded with each page) and the stored pages; no request.

usage: <qwt venv python> -I paging_census190.py OUT_CSV RUN [RUN ...]
       (PSYCOPG_IMPL=python and the pgserver bin on PATH, as for runinfo190.py)
"""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, "C:/m8/live")
from runinfo190 import E, q  # noqa: E402

DATA = Path("C:/m8/q190/data/runs/marianos-53100502-pickup")
TILE = re.compile(r'data-testid="(?:horizontal|default)-product-card-(\d+)"')
RANK = re.compile(r'"searchEngineRank":(\d+),"upc":"(\d{13})"')
LOADED = re.compile(r'"loadedPages":\[([0-9,]*)\]')
SEARCH = re.compile(r'"totalCount":(\d+),"availableCount":(\d+),"searchId":"([^"]*)"')
BRANDS = re.compile(r'"brands":\[\{"name"')
FIELDS = ["run_id", "asked_utc", "listing", "page_asked", "fetch_id", "provider_request_id", "run_js_requested",
          "rendered_by_provider", "ms", "loaded_pages", "tiles", "ranked_products", "rank_first", "rank_last",
          "same_products_as_page_1", "products_new_to_the_listing", "class", "total_count", "available_count",
          "search_id", "search_id_same_as_page_1", "brand_facet_in_state", "stored_page_sha256"]


def organic(html: str) -> list[tuple[int, str]]:
    out: dict[str, int] = {}
    for r, u in RANK.findall(html):
        if int(r) > 0:
            out[u] = max(int(r), out.get(u, 0))
    return sorted(((r, u) for u, r in out.items()))


def main(out_csv: str, runs: list[str]) -> None:
    import hashlib

    rows = []
    with E.connect() as c:
        for run in runs:
            meta = {}
            for e in q(c, "select data from events where run_id=:r and code='SESSION_PAGE_CAPTURED'", r=run):
                d = e["data"] if isinstance(e["data"], dict) else json.loads(e["data"])
                meta[d.get("fetch_id")] = d
            fetches = q(c, "select id, started_at, url, duration_ms from page_fetches where run_id=:r and "
                           "purpose='listing' order by started_at", r=run)
            first: dict[str, set[str]] = {}
            first_sid: dict[str, str] = {}
            seen: dict[str, set[str]] = {}
            earlier_answer: dict[tuple[str, int], set[str]] = {}
            for f in fetches:
                u = urlsplit(f["url"])
                listing = u.path.rstrip("/").rsplit("/", 1)[-1]
                page = int((parse_qs(u.query).get("page") or ["1"])[0])
                p = DATA / run / "live" / "dom" / f"{f['id']}.html.gz"
                b = p.read_bytes() if p.exists() else b""
                html = gzip.decompress(b).decode("utf-8", "replace") if b else ""
                org = organic(html)
                ups = {x for _, x in org}
                lp = LOADED.findall(html)[:1]
                sm = SEARCH.findall(html)[:1]
                sid = sm[0][2] if sm else ""
                if page == 1 and sid:
                    first_sid.setdefault(listing, sid)
                m = meta.get(f["id"], {})
                same = None
                if page == 1 and ups:
                    first.setdefault(listing, ups)
                elif ups and listing in first:
                    same = ups == first[listing]
                new = len(ups - seen.get(listing, set())) if ups else 0
                seen.setdefault(listing, set()).update(ups)
                again = earlier_answer.get((listing, page))
                if ups:
                    earlier_answer[(listing, page)] = ups
                if not html:
                    cls = "no stored page"
                elif not ups:
                    cls = "no ranked products"
                elif again is not None and again == ups:
                    cls = "asked again: the same products as the earlier answer for this page"
                elif page == 1:
                    cls = "page 1"
                elif same:
                    cls = "repeats page 1"
                elif new == 0:
                    cls = "only earlier products"
                else:
                    cls = "distinct page"
                rows.append({
                    "run_id": run, "asked_utc": f["started_at"].strftime("%Y-%m-%dT%H:%M:%SZ"), "listing": listing,
                    "page_asked": page, "fetch_id": f["id"], "provider_request_id": m.get("request_id", ""),
                    "run_js_requested": m.get("run_js_requested", ""), "rendered_by_provider": m.get("rendered", ""),
                    "ms": f["duration_ms"], "loaded_pages": lp[0] if lp else "", "tiles": len(TILE.findall(html)),
                    "ranked_products": len(org), "rank_first": org[0][0] if org else "",
                    "rank_last": org[-1][0] if org else "",
                    "same_products_as_page_1": "" if same is None else ("yes" if same else "no"),
                    "products_new_to_the_listing": new, "class": cls,
                    "total_count": sm[0][0] if sm else "", "available_count": sm[0][1] if sm else "",
                    "search_id": sid,
                    "search_id_same_as_page_1": "" if page == 1 or not sid or listing not in first_sid
                    else ("yes" if sid == first_sid[listing] else "no"),
                    "brand_facet_in_state": ("yes" if BRANDS.search(html) else "no") if html else "",
                    "stored_page_sha256": hashlib.sha256(b).hexdigest() if b else "",
                })
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    from collections import Counter

    print(json.dumps({"rows": len(rows), "by_class": Counter(r["class"] for r in rows),
                      "rendered_with_tiles": sum(1 for r in rows if r["rendered_by_provider"] is True and r["tiles"]),
                      "rendered_without_tiles": sum(1 for r in rows if r["rendered_by_provider"] is True
                                                    and not r["tiles"]),
                      "unrendered_with_tiles": sum(1 for r in rows if r["rendered_by_provider"] is False and r["tiles"]),
                      "unrendered_without_tiles": sum(1 for r in rows if r["rendered_by_provider"] is False
                                                      and not r["tiles"])}, default=str))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
