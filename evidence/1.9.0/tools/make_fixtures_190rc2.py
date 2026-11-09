"""Build the release 1.9.0rc2 fixtures (the tile Mariano's serves since 2026-11-06) in
tests/fixtures/oxylabs_2026-11-06: real pages only, nothing edited.

- s1_*.html.gz: pages stage S1 saved (run 01M6S5MYBC05W3S308EC7XWTGV, Cat Food 27021 page 1, 2026-11-06), copied
  byte for byte from the run's data folder (the collector's sanitized copy; the SHA-256 equals the run's artifact).
- o2_*.html.gz: provider answers of stage O2 (C:/m8/evidence/live190/o2/captures), their result HTML passed through
  the collector's sanitizer (as the collector stores pages), gzip with mtime 0.
- SOURCES_TILES.json: for each file its origin (run, fetch or capture, request id, provider's run_js statement,
  hashes).

usage: make_fixtures_190rc2.py OUT_DIR
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path

from marianos_headless.sites.marianos.sanitize import sanitize_html

OUT = Path(sys.argv[1])
S1 = Path("C:/m8/q190/data/runs/marianos-53100502-pickup/01M6S5MYBC05W3S308EC7XWTGV/live/dom")
S1_LOG = Path("C:/m8/evidence/live190/logs/S1.log")
O2 = Path("C:/m8/evidence/live190/o2/captures")

s1_pages = {
    "s1_catfood_p1_rendered_nogrid.html.gz": "01M6S5N6KJTSK5GDR5W1TXMSTQ",
    "s1_catfood_p1_tiles.html.gz": "01M6S5RDC5TP4XK2CV3TGTMG52",
}
o2_pages = {
    "o2_cattreats_p1_tiles.html.gz": "01_t1_cattreats_p1",
    "o2_cattreats_p2_rendered_nogrid.html.gz": "02_t2_cattreats_p2",
    "o2_search_bananas_tiles.html.gz": "04_t5_search_bananas",
    "o2_dogfood_p1_tiles.html.gz": "05_t6_dogfood_p1",
    "o2_search_nutrl_tiles.html.gz": "06_t7_search_nutrl",
    "o2_search_purina_one_tiles.html.gz": "07_t8_search_purina_one",
}

captured = {}
for raw_line in S1_LOG.read_bytes().splitlines():
    # The console log mixes UTF-8 and the Windows console code page (cp1252: "›" written as 0x9B):
    # each line is decoded strictly, one way or the other; an undecodable line stops the build.
    try:
        line = raw_line.decode("utf-8")
    except UnicodeDecodeError:
        line = raw_line.decode("cp1252")
    if '"SESSION_PAGE_CAPTURED"' in line:
        rec = json.loads(line)
        d = rec.get("data") or {}
        captured[d.get("fetch_id")] = d
missing = [f for f in s1_pages.values() if f not in captured]
assert not missing, f"no SESSION_PAGE_CAPTURED event for {missing}"

sources: dict[str, dict] = {}
for name, fetch_id in s1_pages.items():
    raw = (S1 / f"{fetch_id}.html.gz").read_bytes()
    (OUT / name).write_bytes(raw)
    d = captured[fetch_id]
    sources[name] = {
        "stage": "M-S1-canary-catfood-190-20261106",
        "run_id": "01M6S5MYBC05W3S308EC7XWTGV",
        "fetch_id": fetch_id,
        "url": "https://www.marianos.com/pl/cat-food/27021",
        "request_id": d.get("request_id"),
        "requested_run_js": d.get("run_js_requested"),
        "provider_run_js": d.get("rendered"),
        "fetched_at": d.get("at"),
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "origin": f"runs/marianos-53100502-pickup/01M6S5MYBC05W3S308EC7XWTGV/live/dom/{fetch_id}.html.gz (byte copy)",
    }
for name, cap in o2_pages.items():
    env = json.loads(gzip.decompress((O2 / f"{cap}.raw.gz").read_bytes()))
    rec = json.loads((O2 / f"{cap}.json").read_text(encoding="utf-8"))
    r0 = env["results"][0]
    sanitized, report = sanitize_html(r0["html"])
    body = sanitized.encode("utf-8")
    (OUT / name).write_bytes(gzip.compress(body, mtime=0))
    sources[name] = {
        "stage": "M-O2-tile-discovery-190-20261106",
        "capture": f"C:/m8/evidence/live190/o2/captures/{cap}.raw.gz",
        "capture_sha256": rec.get("raw_sha256"),
        "request_id": rec.get("request_id"),
        "endpoint": rec.get("endpoint"),
        "requested": rec.get("body_sent"),
        "provider_run_js": (r0.get("metadata") or {}).get("run_js"),
        "fetched_at": rec.get("utc_start"),
        "sanitized_html_sha256": hashlib.sha256(body).hexdigest(),
        "sanitize": {"input_sha256": report.input_sha256, "output_sha256": report.output_sha256},
    }
(OUT / "SOURCES_TILES.json").write_text(json.dumps(sources, indent=1) + "\n", encoding="utf-8", newline="\n")
for name in sorted(sources):
    print(name, (OUT / name).stat().st_size, sources[name].get("provider_run_js"))
