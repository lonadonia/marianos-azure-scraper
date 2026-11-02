"""Index of the Classic documentation pages saved 2026-11-02 (classic_docs_20261102/index.json) and the probe's
DOCUMENTED_CONTRACT note on it. Each page's URL is the one its own first line names; the one Page Not Found page
names none, so its URL is the one requested (from its file name, as the page's own text confirms)."""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

D = Path(r"C:\m6\classic\docs_20261102")
CONTRACT = Path(r"C:\m5\wt\headless\oxylabs-classic-probe\docs\DOCUMENTED_CONTRACT.md")
ct = CONTRACT.read_bytes().decode("utf-8")
# The 2026-10-31 hashes, from the contract's own table (URL -> SHA-256).
old = {
    m.group(1): m.group(3)
    for m in re.finditer(r"\| (https://developers\.oxylabs\.io/\S+\.md) \| (2026-10-31T[0-9:]+Z) \| `([0-9a-f]{64})` \|", ct)
}
assert len(old) == 12, len(old)
items = []
for f in sorted(D.glob("*.md")):
    b = f.read_bytes()
    t = b.decode("utf-8")
    first = t.split("\n", 1)[0]
    m = re.search(r"this page is available as \[Markdown\]\((https://developers\.oxylabs\.io/[^)]+\.md)\)", first)
    nf = first.strip() == "# Page Not Found"
    if m:
        url, url_from = m.group(1), "the page's own first line"
    else:
        assert nf, f.name
        assert "web-scraper-api/targets/marianos` does not exist" in t
        url = "https://developers.oxylabs.io/" + f.stem.replace("_", "/") + ".md"
        url_from = "the request (the page names no URL of its own; its text says web-scraper-api/targets/marianos does not exist)"
    sha = hashlib.sha256(b).hexdigest()
    saved = dt.datetime.fromtimestamp(f.stat().st_mtime, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    items.append(
        {
            "file": f.name,
            "url": url,
            "url_from": url_from,
            "bytes": len(b),
            "saved_utc": saved,
            "sha256": sha,
            "page_not_found": nf,
            "same_as_2026_10_31": (old[url] == sha) if url in old else None,
        }
    )
idx = {
    "what": "Oxylabs Web Scraper API public documentation pages, each downloaded once with curl on 2026-11-02 "
    "(no provider API was called). same_as_2026_10_31: true when the SHA-256 equals the copy of 2026-10-31 listed "
    "in the Classic probe's docs/DOCUMENTED_CONTRACT.md; null when no copy of that date exists.",
    "pages": items,
}
(D / "index.json").write_bytes((json.dumps(idx, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
same = [i["file"] for i in items if i["same_as_2026_10_31"]]
diff = [i["file"] for i in items if i["same_as_2026_10_31"] is False]
print(len(items), "pages;", len(same), "same as 10-31;", "differ:", diff)
for i in items:
    print(i["saved_utc"], i["sha256"][:12], i["page_not_found"], i["same_as_2026_10_31"], i["url"])
