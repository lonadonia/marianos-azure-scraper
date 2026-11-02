"""Offline: the collector's own store check on the saved L1 page, against the expected Vernon Hills entry."""
from __future__ import annotations

import glob
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\m5\wt\headless\marianos-azure-headless\src")
from marianos_headless.core.settings import StoreConfig  # noqa: E402
from marianos_headless.sites.marianos.initial_state import parse_initial_state  # noqa: E402
from marianos_headless.sites.marianos import store_context as sc  # noqa: E402

f = sorted(glob.glob(r"C:\m6\ev\probes\*_L1.html.gz"))[-1]
html = gzip.decompress(Path(f).read_bytes()).decode("utf-8")
st = parse_initial_state(html)
print("functions:", [n for n in dir(sc) if not n.startswith("_")][:40])
mod = st.get("modalitySelectorState")
print("modalitySelectorState", json.dumps(mod, default=str)[:1500])
print("toggle storeInfo keys")
for k in ("calypso",):
    v = st.get(k) or {}
    print(k, sorted(v)[:20] if isinstance(v, dict) else type(v))
import re
for pat in (r"1720[^\"<]{0,60}", r"Vernon Hills[^\"<]{0,40}", r"60061[^\"<]{0,20}", r"Shorewood[^\"<]{0,30}", r"Lakeshore East[^\"<]{0,30}"):
    hits = re.findall(pat, html)
    print(pat, len(hits), list(dict.fromkeys(hits))[:5])
