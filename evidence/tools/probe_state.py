"""PRIVATE: print the search state's productsInfo of stored pages (fetch ids), with the collector's own extraction."""
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, "[redacted:workstation-path]/wt/headless/marianos-azure-headless/src")
from marianos_headless.sites.marianos.initial_state import parse_initial_state as extract_initial_state  # noqa: E402
from marianos_headless.sites.marianos.search_state import brand_facets, listing_children  # noqa: E402

d = Path(sys.argv[1])
for arg in sys.argv[2:]:
    fid, tax = arg.split(":")
    h = gzip.decompress((d / f"{fid}.html.gz").read_bytes()).decode("utf-8", "replace")
    st = extract_initial_state(h)
    sa = st.get("search", {}).get("searchAll", {})
    resp = sa.get("response") if isinstance(sa, dict) else None
    info = (resp or {}).get("productsInfo") if isinstance(resp, dict) else None
    print("==", fid, tax, "searchAll keys:", list(sa.keys())[:12] if isinstance(sa, dict) else type(sa))
    print("   response keys:", list(resp.keys())[:20] if isinstance(resp, dict) else resp)
    print("   productsInfo keys:", list(info.keys()) if isinstance(info, dict) else info)
    if isinstance(info, dict):
        deps = info.get("departments") or []
        def walk(n, depth=0):
            if not isinstance(n, dict) or depth > 3:
                return
            kids = n.get("categories") or n.get("subcategories") or []
            print("   " + "  " * depth, n.get("id"), n.get("name"), n.get("count"), "slug" if n.get("slug") else "-", len(kids))
            for k in kids[:40]:
                walk(k, depth + 1)
        for dd in deps:
            walk(dd)
        print("   brands:", len(info.get("brands") or []), (info.get("brands") or [])[:3])
    print("   collector: children", len(listing_children(st, tax)), "brands", len(brand_facets(st)))
