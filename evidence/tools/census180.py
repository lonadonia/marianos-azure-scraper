"""TEST_PLAN_180 Amendment 8: department census at 53100502 PICKUP (stage OXP/D). One submission per department,
sequential, no retry; reserve before dispatch; sanitized page kept; key read only through load_key().

    <collector venv python> -X utf8 census180.py

Writes C:/m6/ev/census/<stamp>_D<dept>.json (+ .html.gz) and census.jsonl. Stops on a refusal or block, a page of
another store or fulfillment, or three provider failures in a row. Departments with an assumed slug are sent only if
the first assumed-slug request (40) came back as department 40 (the slug is cosmetic)."""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, r"C:\m6\tools")
import budget180  # noqa: E402
import probe180  # noqa: E402
from probe180 import BASE, RATE, analyse, key, oxylabs, sanitize_html, stamp  # noqa: E402

OUT = Path(r"C:\m6\ev\census")
LOG = OUT / "census.jsonl"
STORE, FULFILMENT = "53100502", "pickup"
CONTROL = [("27", "pet", True)]
SLUG_TEST = [("40", "dining", False)]
KNOWN = [("01", "pantry", True), ("02", "dairy-eggs", True), ("05", "meat-seafood", True),
         ("06", "fresh-fruits-vegetables", True), ("13", "deli", True), ("18", "natural-organic", True),
         ("20", "beauty", True), ("21", "personal-care", True), ("22", "health-wellness", True),
         ("26", "cleaning-and-household", True), ("28", "kitchen", True)]
ASSUMED = [("04", "beverages", False), ("08", "beer-wine-liquor", False), ("09", "floral", False),
           ("10", "baby", False), ("14", "bakery", False), ("19", "frozen", False), ("23", "candy", False)]


def departments(html: str) -> list[dict]:
    i = html.find('"departments":[')
    if i < 0:
        return []
    try:
        val, _ = json.JSONDecoder().raw_decode(html, i + len('"departments":'))
    except ValueError:
        return []
    out = []
    for d in val if isinstance(val, list) else []:
        cats = [{"id": c.get("id"), "name": c.get("name"), "count": c.get("count"),
                 "subcategories": len(c.get("subcategories") or [])} for c in d.get("categories") or []]
        out.append({"id": d.get("id"), "name": d.get("name"), "slug": d.get("slug"), "count": d.get("count"),
                    "categories": cats})
    return out


def send(dept: str, slug: str, slug_known: bool) -> dict:
    k = key()
    url = f"https://www.marianos.com/pl/{slug}/{dept}"
    body = {"url": url, "store_id": STORE, "fulfillment_type": FULFILMENT, "location": "US", "output": ["html"]}
    rid = budget180.reserve("OXP", "D", RATE, note=f"D{dept}: department census {url}"[:300])
    at, t0 = stamp(), time.monotonic()
    rec: dict = {"id": f"D{dept}", "at": at, "department": dept, "slug": slug, "slug_known": slug_known, "url": url,
                 "ledger": rid}
    try:
        with httpx.Client(base_url=BASE, timeout=180) as c:
            r = c.post("/v1/scrape/marianos", json=body,
                       headers={"Authorization": f"Bearer {k.get_secret_value()}"})
    except httpx.HTTPError as exc:
        budget180.settle(rid, RATE, outcome=f"D{dept}: transport {type(exc).__name__}, possibly charged")
        rec.update(kind=f"transport {type(exc).__name__}", seconds=round(time.monotonic() - t0, 1))
        return rec
    rec["seconds"] = round(time.monotonic() - t0, 1)
    html, meta = oxylabs.envelope(r.content)
    kind = oxylabs.classify(r.status_code, r.content, html)
    charged = oxylabs.CHARGED.get(kind)
    budget180.settle(rid, RATE if charged is None or charged else 0.0,
                     outcome=f"D{dept}: HTTP {r.status_code} kind {kind} charged {charged}")
    rec.update(status=r.status_code, kind=kind, charged=charged, request_id=meta.get("request_id"),
               problem={x: meta[x] for x in ("title", "detail", "state") if x in meta})
    if html:
        clean, _ = sanitize_html(html)
        rec["body_sha256"] = hashlib.sha256(clean.encode()).hexdigest()
        (OUT / f"{at}_D{dept}.html.gz").write_bytes(gzip.compress(clean.encode("utf-8"), mtime=0))
        a = analyse(html)
        s = a.get("summary") or {}
        rec.update(location_id=s.get("location_id"), modality=s.get("modality"), total=s.get("total"),
                   available=s.get("available"), taxonomy_id=s.get("taxonomy_id"),
                   state_products=a.get("state_products"), departments=departments(html))
    return rec


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print("key fingerprint", oxylabs.fingerprint(key()))
    plan = CONTROL + SLUG_TEST + KNOWN
    fails = 0
    i = 0
    while i < len(plan):
        dept, slug, known = plan[i]
        rec = send(dept, slug, known)
        with LOG.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        (OUT / f"{rec['at']}_D{dept}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False), "utf-8")
        deps = rec.get("departments") or []
        print(time.strftime("%H:%M:%SZ", time.gmtime()), rec["id"], rec.get("status"), rec.get("kind"),
              rec.get("seconds"), "store", rec.get("location_id"), rec.get("modality"), "total", rec.get("total"),
              "deps", [(d["id"], d["slug"], d["count"], len(d["categories"])) for d in deps], flush=True)
        kind = str(rec.get("kind"))
        if any(w in kind for w in ("block", "refus", "captcha", "denied")):
            print("STOP: refusal or block", kind)
            break
        if rec.get("location_id") not in (None, STORE) or (rec.get("modality") not in (None, "PICKUP")):
            print("STOP: another store or fulfillment", rec.get("location_id"), rec.get("modality"))
            break
        ok = rec.get("status") == 200 and rec.get("total") is not None
        fails = 0 if ok else fails + 1
        if fails >= 3:
            print("STOP: three provider failures in a row")
            break
        if dept == "40":
            cosmetic = any(d.get("id") == "40" for d in deps)
            print("slug test (40):", "cosmetic: assumed slugs are sent" if cosmetic else "NOT shown: assumed slugs skipped")
            if cosmetic:
                plan = plan + ASSUMED
        i += 1
    budget180.status()


if __name__ == "__main__":
    main()
