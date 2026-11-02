"""Q1b's Candles page 1 (live 2026-11-02 12:30Z, run 01M6E3RDEBPZ39SVR37JR6PE8F): the grid's mini-product-card variant."""
import gzip
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, r"C:\m5\wt\headless\marianos-azure-headless\src")
from marianos_headless.sites.marianos.sanitize import sanitize_html  # noqa: E402

SRC = Path(
    r"C:\m6\q180\data\runs\marianos-53100502-pickup\01M6E3RDEBPZ39SVR37JR6PE8F\live\dom"
    r"\01M6E3RJKJY07V4S1323J8VR52.html.gz"
)
OUT = Path(r"C:\m5\wt\headless\marianos-azure-headless\tests\fixtures\oxylabs_2026-11-02")
html = gzip.decompress(SRC.read_bytes()).decode("utf-8")
clean, _ = sanitize_html(html)
data = gzip.compress(clean.encode("utf-8"), 9, mtime=0)
(OUT / "listing_32001_p1_mini.html.gz").write_bytes(data)
sha = hashlib.sha256(html.encode("utf-8")).hexdigest()[:16]
readme = OUT / "README.md"
t = readme.read_bytes().decode("utf-8")
assert "listing_32001_p1_mini" not in t
t = t.replace(
    "qualification run Q1 (its first listing page, as the collector stored it) on 2026-11-02, and",
    "qualification runs Q1 and Q1b (their first listing page, as the collector stored it) on 2026-11-02, and",
)
row = (
    "| listing_32001_p1_mini.html.gz | Q1b | the same page 13 minutes later (qualification run "
    "01M6E3RDEBPZ39SVR37JR6PE8F of 1.8.0rc2): the same 24 products as mini-product-card-N cards | "
    f"{sha} (of the copy the collector stored, already sanitized) |\n"
)
t = t.rstrip("\n") + "\n" + row
readme.write_bytes(t.encode("utf-8"))
print("ok", len(html), len(clean), len(data), sha, clean == html)
