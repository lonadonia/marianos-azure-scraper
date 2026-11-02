"""Real Vernon Hills probe pages as test fixtures, each through the collector's own HTML sanitizer."""
import glob
import gzip
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, r"C:\m5\wt\headless\marianos-azure-headless\src")
from marianos_headless.sites.marianos.sanitize import sanitize_html  # noqa: E402

OUT = Path(r"C:\m5\wt\headless\marianos-azure-headless\tests\fixtures\oxylabs_2026-11-02")
OUT.mkdir(parents=True, exist_ok=True)
NAMES = {
    "L1": ("search_cereal_p1.html.gz", "the search for cereal, first page"),
    "L18": ("search_cereal_p2.html.gz", "the search for cereal, page=2: the 24 products of page 1 again, ranks 25-48"),
    "L2": ("listing_03001_p1.html.gz", "/pl/cereal-granola/03001, page 1, without rendering"),
    "L9": ("listing_03001_p2_no_js.html.gz", "the same listing, page=2, without rendering: page state without cards"),
    "L10": ("listing_03001_p2.html.gz", "the same listing, page=2, rendered"),
    "L20": ("listing_0300100001_brand.html.gz", "/pl/cold-cereal/0300100001?brandName=General%20Mills"),
}
rows = []
for probe, (name, what) in NAMES.items():
    src = sorted(glob.glob(rf"C:\m6\ev\probes\*_{probe}.html.gz"))[-1]
    meta = json.loads(Path(src[: -len(".html.gz")] + ".json").read_text(encoding="utf-8"))
    html = gzip.decompress(Path(src).read_bytes()).decode("utf-8")
    clean, n = sanitize_html(html)
    data = gzip.compress(clean.encode("utf-8"), 9, mtime=0)
    (OUT / name).write_bytes(data)
    rows.append((name, probe, what, len(data), hashlib.sha256(html.encode("utf-8")).hexdigest()[:16], n))
    print(name, len(html), len(clean), len(data), n)
lines = [
    "# Real pages of 2026-11-02 (store 53100502, Marianos Vernon Hills, Pickup)",
    "",
    "FIXTURE: pages captured live through the Oxylabs Web API by probes L1, L2, L9, L10, L18 and L20 on 2026-11-02 and",
    "replayed offline, each through the collector's own HTML sanitizer. A test that uses them is a replay, never a",
    "live run.",
    "",
    "| File | Probe | What | First 16 hex of the raw page's SHA-256 |",
    "|---|---|---|---|",
]
for name, probe, what, _, sha, _ in rows:
    lines.append(f"| {name} | {probe} | {what} | {sha} |")
(OUT / "README.md").write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
print("ok")
