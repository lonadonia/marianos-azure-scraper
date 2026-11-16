"""PRIVATE OPS (owner VM, root): every Coupons-route reading the runs recorded, set beside the stored page it was
read from. Read only, no network.

    python3.12 -I coupons_route_check.py OUT.txt DB [DB ...]

For each run whose counts hold a `coupons_route` reading: the run, the collector's recorded status and coupon_cards,
the fetch; and from the stored page (`live/dom/<fetch>.html.gz` in the run's folder): its SHA-256 (of the stored
file, as the run's provenance names pages) and size, the coupon cards it holds (`data-testid="coupon-grid-card"`),
and whether the coupons tab holds the site's loading indicator in place of a list.
"""

from __future__ import annotations

import glob
import gzip
import hashlib
import json
import subprocess
import sys

OUT, DBS = sys.argv[1], sys.argv[2:]
SPINNER = '<div class="pt-32 heading-xl text-center"><div data-citrus-component="LoadingIndicator"'
ROOTS = ("/var/lib/marianos-collector/*/data/runs/*", "/var/lib/marianos-collector/data/runs/*",
         "/var/lib/marianos-collector/*/runs/*")
L = ["Coupons route (CSV row 0, /savings/cl/coupons/): each reading the runs recorded, beside its stored page.",
     "recorded = the collector's own verdict (run counts 'coupons_route'); page = the stored page as kept;",
     "cards = coupon cards in the page (data-testid=\"coupon-grid-card\"); tab spinner = the coupons tab shows the",
     "site's loading indicator instead of a list.", ""]
for db in DBS:
    q = ("SELECT id, to_char(started_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'), counts->'coupons_route' "
         "FROM runs WHERE counts ? 'coupons_route' ORDER BY started_at")
    r = subprocess.run(["sudo", "-u", "marianos", "psql", "-X", "-At", "-F", "\t", "-d", db, "-c", q],
                       capture_output=True, text=True, check=True)
    for row in r.stdout.splitlines():
        run, started, cj = row.split("\t")
        c = json.loads(cj)
        fid = c.get("fetch_id") or ""
        files = sorted({f for root in ROOTS for f in glob.glob(f"{root}/{run}/live/dom/{fid}.html.gz")}) if fid else []
        L.append(f"run {run} (started {started}Z)")
        L.append(f"  recorded  status {c.get('status')!r}, coupon_cards {c.get('coupon_cards')}, store_check "
                 f"{c.get('store_check')!r}, run_js {c.get('run_js')}, fetch {fid or '-'}")
        if len(files) != 1:
            L.append(f"  page      {'not stored' if not files else 'more than one copy: ' + str(len(files))}")
            L.append("")
            continue
        raw = open(files[0], "rb").read()
        html = gzip.decompress(raw).decode("utf-8", errors="replace")
        cards = html.count('data-testid="coupon-grid-card"')
        spin = SPINNER in html
        L.append(f"  page      live/dom/{fid}.html.gz sha256 {hashlib.sha256(raw).hexdigest()} ({len(html):,} "
                 f"characters)")
        L.append(f"  read      cards {cards}; tab spinner {'YES' if spin else 'no'} -> "
                 + ("the list had NOT loaded: 0 cards is not 'no coupons'" if spin and not cards else
                    ("the list loaded" if cards and not spin else "neither cards nor a spinner: undetermined")))
        L.append("")
open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print("\n".join(L))
