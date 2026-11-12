"""Builds tests/fixtures/oxylabs_2026-11-09/ for release 1.10.0 (C1): byte copies of pages the collector stored
during the live stages of 2026-11-09 (store 53100502, Pickup), named by what they show, with their origins.

    python -I make_fixtures_1100.py <collector folder>

Reads the paging census of the 1.9.0 evidence for each page's request (time, provider request ID, hash) and the
stage runs' own stored pages (kept privately); writes the copies, SOURCES.json and nothing else. A copy whose
hash differs from the census is refused."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

CENSUS = Path("C:/m7/repo/evidence/1.9.0/live/PAGING_CENSUS_190.csv")
DATA = Path("C:/m8/q190/data/runs/marianos-53100502-pickup")
S4, S5A, S3B = "01M70BG79WGW9EC5ZTW2M4V4XS", "01M70C404FTCMYSY621EKJ015X", "01M70H9RB4Q736926MP3W5117A"
STAGES = {S4: ("S4", "1.9.0rc3"), S5A: ("S5a", "1.9.0rc3"), S3B: ("S3b", "1.9.0rc4")}
URLS = {
    "26003": "https://www.marianos.com/pl/batteries/26003",
    "18010": "https://www.marianos.com/pl/frozen/18010",
}
# (run, listing, page asked) -> (file name, what the page shows)
WANT = {
    (S4, "26003", 1): (
        "s4_batteries_p1.html.gz",
        "Batteries page 1: 24 products of 96; the page state names no brand and no child listing",
    ),
    (S4, "26003", 2): (
        "s4_batteries_p2_repeats_p1.html.gz",
        "Batteries, page 2 asked: the answer states page 2 and ranks 25 to 48, and lists page 1's 24 products",
    ),
    (S5A, "26003", 2): (
        "s5a_batteries_p2.html.gz",
        "Batteries page 2, asked 6 min 33 s after the repeated answer: 24 other products (and 4 sponsored)",
    ),
    (S5A, "26003", 3): ("s5a_batteries_p3.html.gz", "Batteries page 3: 24 other products (and 3 sponsored)"),
    (S5A, "26003", 4): ("s5a_batteries_p4.html.gz", "Batteries page 4: the last 24 of 96 (and 5 sponsored)"),
    (S3B, "18010", 1): (
        "s3b_frozen_p1_no_filters.html.gz",
        "Frozen page 1: 273 results, 250 reachable; the page state names no brand and no child listing",
    ),
    (S3B, "18010", 2): (
        "s3b_frozen_p2_repeats_p1.html.gz",
        "Frozen, page 2 asked: the answer states page 2 and lists page 1's 24 products",
    ),
}


def main() -> int:
    dest = Path(sys.argv[1]) / "tests" / "fixtures" / "oxylabs_2026-11-09"
    dest.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(CENSUS.open(encoding="utf-8")))
    sources: dict[str, dict[str, object]] = {}
    for (run, listing, page), (name, what) in WANT.items():
        found = [
            r for r in rows if r["run_id"] == run and r["listing"] == listing and int(r["page_asked"]) == page
        ]
        assert len(found) == 1, (run, listing, page, len(found))
        r = found[0]
        src = DATA / run / "live" / "dom" / f"{r['fetch_id']}.html.gz"
        raw = src.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        assert sha == r["stored_page_sha256"], (name, sha, r["stored_page_sha256"])
        (dest / name).write_bytes(raw)
        stage, revision = STAGES[run]
        sources[name] = {
            "what": what,
            "stage": stage,
            "collector_revision": revision,
            "run_id": run,
            "fetch_id": r["fetch_id"],
            "url": URLS[listing] + (f"?page={page}" if page > 1 else ""),
            "listing": listing,
            "page_asked": page,
            "asked_utc": r["asked_utc"],
            "provider_request_id": r["provider_request_id"],
            "requested_run_js": r["run_js_requested"],
            "rendered_by_provider": r["rendered_by_provider"],
            "census_class": r["class"],
            "brand_facet_in_state": r["brand_facet_in_state"],
            "file_sha256": sha,
            "bytes": len(raw),
            "origin": f"runs/marianos-53100502-pickup/{run}/live/dom/{r['fetch_id']}.html.gz (byte copy of "
            "the collector's own stored page)",
        }
    (dest / "SOURCES.json").write_bytes((json.dumps(sources, indent=1) + "\n").encode("utf-8"))
    print(f"{len(sources)} pages copied to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
