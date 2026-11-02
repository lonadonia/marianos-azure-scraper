"""Q1's Candles page 1 (live 2026-11-02, run 01M6E2XXQNX1FYXPM37FGTYCKQ) as a replay fixture, through the sanitizer."""
import gzip
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, r"C:\m5\wt\headless\marianos-azure-headless\src")
from marianos_headless.sites.marianos.sanitize import sanitize_html  # noqa: E402

SRC = Path(
    r"C:\m6\q180\data\runs\marianos-53100502-pickup\01M6E2XXQNX1FYXPM37FGTYCKQ\live\dom"
    r"\01M6E2Y2P3C8QJP3S4AC5HSRC5.html.gz"
)
OUT = Path(r"C:\m5\wt\headless\marianos-azure-headless\tests\fixtures\oxylabs_2026-11-02")
html = gzip.decompress(SRC.read_bytes()).decode("utf-8")
clean, report = sanitize_html(html)
assert clean == html or len(clean) <= len(html)
data = gzip.compress(clean.encode("utf-8"), 9, mtime=0)
(OUT / "listing_32001_p1.html.gz").write_bytes(data)
sha = hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
readme = OUT / "README.md"
t = readme.read_bytes().decode("utf-8")
row = (
    "| listing_32001_p1.html.gz | Q1 | /pl/candles-home-fragrances/32001, page 1, rendered (qualification run "
    "01M6E2XXQNX1FYXPM37FGTYCKQ of 1.8.0rc1): UPC 0019798100139's price is stated for no store | "
    f"{sha} |\n"
)
assert "listing_32001_p1" not in t
t = t.replace(
    "FIXTURE: pages captured live through the Oxylabs Web API by probes L1, L2, L9, L10, L18 and L20 on 2026-11-02 and",
    "FIXTURE: pages captured live through the Oxylabs Web API by probes L1, L2, L9, L10, L18 and L20 and by the\n"
    "qualification run Q1 (its first listing page, as the collector stored it) on 2026-11-02, and",
)
t = t.rstrip("\n") + "\n" + row
readme.write_bytes(t.encode("utf-8"))
print("ok", len(html), len(clean), len(data), sha, clean == html)
