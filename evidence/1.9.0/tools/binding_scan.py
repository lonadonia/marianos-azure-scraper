"""M2 evidence: what every saved Mariano's page states about its own search request (filters, search ID binding,
loading flags), so the binding rule is set from real pages, not assumed. Read-only.

Usage: python binding_scan.py <out.csv> <dir or file> [...]
"""

from __future__ import annotations

import csv
import gzip
import sys
from pathlib import Path

from marianos_headless.sites.marianos.initial_state import InitialStateNotFound, dig, parse_initial_state

CORE = ("taxonomyId", "page", "locationId", "activeModalityType", "query")


def main() -> int:
    out = Path(sys.argv[1])
    files: list[Path] = []
    for a in sys.argv[2:]:
        p = Path(a)
        files += sorted(p.rglob("*.html.gz")) if p.is_dir() else [p]
    rows = []
    for f in files:
        try:
            html = gzip.decompress(f.read_bytes()).decode("utf-8", "replace")
            st = parse_initial_state(html)
        except (InitialStateNotFound, ValueError, OSError) as exc:
            rows.append({"file": str(f), "note": f"no state: {type(exc).__name__}"})
            continue
        sa = dig(st, "search", "searchAll", default=None)
        if not isinstance(sa, dict):
            rows.append({"file": str(f), "note": "no search.searchAll"})
            continue
        rv = sa.get("requestVars") or {}
        info = dig(sa, "response", "productsInfo", default={}) or {}
        facets = {k: v for k, v in rv.items() if k not in CORE}
        nonempty = {k: v for k, v in facets.items() if isinstance(v, list) and v}
        scalars = {k: v for k, v in facets.items() if not isinstance(v, list)}
        rows.append(
            {
                "file": str(f),
                "taxonomyId": rv.get("taxonomyId"),
                "query": rv.get("query"),
                "page": rv.get("page"),
                "locationId": rv.get("locationId"),
                "modality": rv.get("activeModalityType"),
                "facet_keys": ";".join(sorted(facets)),
                "nonempty_list_facets": repr(nonempty),
                "scalar_facets": repr(scalars),
                "loaded": sa.get("loaded"),
                "loading": sa.get("loading"),
                "hasError": sa.get("hasError"),
                "latestResponseSearchId": sa.get("latestResponseSearchId"),
                "productsInfo.searchId": info.get("searchId"),
                "ids_equal": sa.get("latestResponseSearchId") == info.get("searchId"),
                "total": info.get("totalCount"),
                "available": info.get("availableCount"),
                "note": "",
            }
        )
    keys: list[str] = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "pages")
    bad = [r for r in rows if r.get("note") or r.get("loaded") is not True or r.get("loading") is not False
           or r.get("hasError") is not False or not r.get("ids_equal")]
    print("pages failing loaded/loading/hasError/searchId binding or without state:", len(bad))
    for r in bad:
        print(" ", Path(r["file"]).name, {k: r.get(k) for k in ("loaded", "loading", "hasError", "ids_equal", "note")})
    print("distinct scalar facets:", sorted({r.get("scalar_facets") for r in rows if r.get("scalar_facets")}))
    print("pages with a non-empty list facet:")
    for r in rows:
        if r.get("nonempty_list_facets") not in (None, "{}"):
            print(" ", Path(r["file"]).name, r["nonempty_list_facets"])
    print("distinct facet key sets:", sorted({r.get("facet_keys") for r in rows if r.get("facet_keys") is not None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
