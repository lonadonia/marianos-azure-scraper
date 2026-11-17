"""Each named product's own page as a run read it (--term-upc), traced from the run's stored captures, offline.
Run with the installed release's Python (it imports the collector's own parser, sites.marianos.pdp_savings).

    python -I pdp_terms6.py OUT.json LIVE_DIR DB_PAGE_FETCHES.csv EXPORT_DIR UPC [UPC ...]
    python -I pdp_terms6.py OUT.json --file UPC=PAGE.html.gz [UPC=PAGE.html.gz ...]      (a stored page alone,
                                                     taken as rendered: a test of the parsing, not of a run)

LIVE_DIR is the run's stored folder `runs/<store>/<run>/live` (dom/ holds each page as answered, raw/ the captures
the collector made of it); DB_PAGE_FETCHES.csv the run's page fetches (a stage's evidence); EXPORT_DIR the run's
export (products.json; provenance.json or .json.gz, whose "records" maps each UPC to its provenance).

For each UPC: every product-page fetch of the run whose URL names it (purpose product_terms), with its time, HTTP
status and the stored page's SHA-256; the collector's own capture of the page's Savings section (raw/*.pdp_savings:
the provider's statement that it ran the page's scripts, the section, its rows, the loading indicator); the same
page parsed again here with the collector's parser, which must give the same rows; and the product's exported record
(digital fields, flags, the reasons of empty fields). Each row of the Savings section: tag, coupon ID, headline,
description, full terms, displayed expiry, days left, action (clip), and whether its own qualifying list names the
product. The verdict says what can be said and no more:
  coupon shown       rendered, loaded, the Savings section lists a coupon whose qualifying products name the UPC
  offer for others   rendered, loaded, a Savings row whose qualifying list does not name the UPC
  no savings shown   rendered (as the provider states), loaded, no Savings row: no offer on that page at that time
  unread: loading    the site's loading indicator, no Savings row: nothing is learnt
  unread: not rendered  the provider states it did not run the page's scripts, no Savings row: nothing is learnt
  unread: rendering not stated  the answer does not say whether the scripts ran, no Savings row: nothing is learnt
  unread: no page    no product page of this UPC was read by the run (its card was not reached, or a limit)
An expiry is stated as displayed; whether a coupon has expired is said only from its own displayed date. Prints a
summary; writes OUT.json.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path

from marianos_headless.sites.marianos.pdp_savings import parse_pdp_savings

csv.field_size_limit(1 << 30)
PDP_UPC = re.compile(r"/p/[^?#]*/(\d{13})(?:[?#]|$)")  # the collector's own pattern (acquisition.oxylabs_session)


def load_json(p: Path) -> object:
    b = p.read_bytes()
    if p.suffix == ".gz":
        b = gzip.decompress(b)
    return json.loads(b)


def page(path: Path) -> dict:
    raw = path.read_bytes()
    html = gzip.decompress(raw).decode("utf-8", "replace") if path.suffix == ".gz" else raw.decode("utf-8", "replace")
    s = parse_pdp_savings(html)
    return {"stored_page": path.name, "sha256_stored": hashlib.sha256(raw).hexdigest(), "section": s.section,
            "loading": s.loading, "rows": [r.as_dict() for r in s.rows]}


def verdict(upc: str, parsed: dict, rendered: object) -> str:
    """``rendered``: the provider's statement (True, False, or None when the answer does not say)."""
    rows = parsed["rows"]
    if rows:  # rows are drawn only by the page's scripts, so the page was rendered whatever the answer says
        return "coupon shown" if any(upc in (r.get("qualifying_upcs") or []) for r in rows) else "offer for others"
    if parsed["loading"]:
        return "unread: loading"
    if rendered is False:
        return "unread: not rendered"
    if rendered is None:
        return "unread: rendering not stated"
    return "no savings shown"


def main() -> int:
    out = Path(sys.argv[1])
    if sys.argv[2] == "--file":
        res = {}
        for spec in sys.argv[3:]:
            upc, path = spec.split("=", 1)
            p = page(Path(path))
            res[upc] = {"reads": [{**p, "verdict": verdict(upc, p, True)}]}  # a stored page alone: taken as rendered
        out.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        for upc, r in res.items():
            for x in r["reads"]:
                print(f"{upc}: {x['verdict']}; section {x['section']}, loading {x['loading']}, rows {len(x['rows'])}"
                      + "".join(f"\n   - {w.get('tag')} {w.get('coupon_id')}: {w.get('headline')!r}; expiry "
                                f"{w.get('expiry_text')!r}; action {w.get('action')!r}; names the product: "
                                f"{upc in (w.get('qualifying_upcs') or [])}" for w in x["rows"]))
        return 0
    live, fetches_csv, export = Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    upcs = sys.argv[5:]
    fetches = list(csv.DictReader(fetches_csv.open(encoding="utf-8", newline="")))
    prod_path = export / "products.json"
    products = load_json(prod_path) if prod_path.exists() else []
    if isinstance(products, dict):
        products = next(v for v in products.values() if isinstance(v, list))
    prov_path = export / "provenance.json" if (export / "provenance.json").exists() else export / "provenance.json.gz"
    prov = load_json(prov_path) if prov_path.exists() else {}
    res: dict[str, dict] = {}
    for upc in upcs:
        reads = []
        for f in fetches:
            m = PDP_UPC.search(f.get("url", ""))
            if f.get("purpose") != "product_terms" or not m or m.group(1) != upc:
                continue
            dom = live / "dom" / f"{f['id']}.html.gz"
            caps = sorted((live / "raw").glob(f"{f['id']}.*pdp_savings*"))
            cap = load_json(caps[0]) if caps else None
            capd = (cap or {}).get("data", {}) if isinstance(cap, dict) else {}
            r = {"fetch_id": f["id"], "url": f["url"], "started_at": f.get("started_at"),
                 "http_status": f.get("http_status"), "challenge": f.get("challenge")}
            if dom.exists():
                p = page(dom)
                r.update(p)
                r["collector_capture"] = caps[0].name if caps else None
                r["provider_ran_scripts"] = capd.get("rendered")
                r["requested_run_js"] = capd.get("requested_run_js")
                r["capture_rows_equal_reparse"] = (capd.get("rows") == p["rows"]) if caps else None
                r["verdict"] = verdict(upc, p, capd.get("rendered"))
            else:
                r["verdict"] = "unread: the page was not stored"
            reads.append(r)
        rec = next((x for x in products if x.get("upc") == upc), None)
        pv = (prov.get("records") or {}).get(upc) if isinstance(prov, dict) else None
        res[upc] = {
            "reads": reads,
            "verdict": reads[-1]["verdict"] if reads else "unread: no page",
            "record": {k: rec.get(k) for k in ("product_title", "category", "regular_price", "sale_price",
                                                "digital_deals_description", "digital_deals_price",
                                                "volume_deals_description", "volume_deals_price", "weight", "ppm",
                                                "crawl_date")} if rec else None,
            "record_status": (pv or {}).get("status"), "record_kind": (pv or {}).get("observation_kind"),
            "flags": (pv or {}).get("flags"), "reasons": (pv or {}).get("reasons"),
            "empty_field_reasons": {k: v for k, v in ((pv or {}).get("missing") or {}).items() if "digital" in k},
            "empty_field_kinds": {k: v for k, v in ((pv or {}).get("missing_kind") or {}).items() if "digital" in k},
        }
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for upc, r in res.items():
        print(f"{upc}: {r['verdict']}; {len(r['reads'])} product-page read(s); record "
              f"{r['record_status'] or 'not exported'} ({r['record_kind'] or '-'}); digital: "
              f"{(r['record'] or {}).get('digital_deals_description')!r}; flags {r['flags']}")
        for x in r["reads"]:
            print(f"   read {x['fetch_id']} at {x['started_at']}: HTTP {x['http_status']}, scripts run "
                  f"{x.get('provider_ran_scripts')}, section {x.get('section')}, loading {x.get('loading')}, rows "
                  f"{len(x.get('rows') or [])}, the collector's capture equals the re-parse: "
                  f"{x.get('capture_rows_equal_reparse')}")
            for w in x.get("rows") or []:
                print(f"     - {w.get('tag')} {w.get('coupon_id')}: {w.get('headline')!r}; expiry "
                      f"{w.get('expiry_text')!r}; action {w.get('action')!r}; names the product: "
                      f"{upc in (w.get('qualifying_upcs') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
